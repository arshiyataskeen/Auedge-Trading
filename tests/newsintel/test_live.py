"""Live news intel: phase, event choice, surprise, expected move, chances, similar releases, failure modes.

Synthetic tests use a 1-minute random walk turned into the candle sets the live feed supplies (futures 5m/15m/1h/4h,
daily gold sessions, each with a forming last candle) and a fake Artifacts with known numbers. The real-data tests
(feature parity on the 1-minute backup, FRED surprise dry-run) skip cleanly when their data or key is missing.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from core.indicators import atr
from core.models import Candle, CandleSet, MarketContext
from core.newsintel import live
from core.newsintel.bars import NY, resample, session_day_candles, window
from core.newsintel.features import features
from core.newsintel.fred import first_releases
from core.newsintel.minutes import Minutes
from core.newsintel.ml.data import FEATURE_NAMES
from core.newsintel.ml.export import Artifacts
from core.newsintel.ml.metrics import apply_temperature
from core.newsintel.surprise import expectations

ROOT = Path(__file__).resolve().parents[2]
NPZ = ROOT / "data" / "news_intel" / "xau_1m.npz"
DB = ROOT / "data" / "news_intel.db"

T = int(datetime(2024, 3, 12, 8, 30, tzinfo=NY).timestamp())  # a CPI release time (Tuesday)
COL = {n: i for i, n in enumerate(FEATURE_NAMES)}


# ---------------------------------------------------------------- fixtures

def _walk(seed: int, t_end: int, days: int = 40, drift: float = 0.02, start: int | None = None) -> Minutes:
    """Continuous 1-minute random walk ending just before t_end (optionally starting at `start`)."""
    n = days * 1440
    t = t_end - 60 * np.arange(n, 0, -1)
    if start is not None:
        t = t[t >= start]
    rng = np.random.default_rng(seed)
    c = 2000.0 + np.cumsum(rng.normal(drift, 0.4, len(t)))
    o = np.concatenate([[c[0]], c[:-1]])
    return Minutes(t.astype(np.int64), o, np.maximum(o, c) + 0.2, np.minimum(o, c) - 0.2, c)


def _merge(m: Minutes, a: int, b: int, t: int) -> Candle | None:
    s = window(m, a, b)
    if s.stop <= s.start:
        return None
    return Candle(t=t, o=float(m.o[s.start]), h=float(m.h[s].max()), l=float(m.l[s].min()), c=float(m.c[s.stop - 1]))


def _session_start(now: int) -> tuple[int, int]:
    """(start of the gold session forming at `now`, 00:00 NY of the day it ends)."""
    d = datetime.fromtimestamp(now, NY).date()
    if now >= int(datetime(d.year, d.month, d.day, 17, tzinfo=NY).timestamp()):
        d += timedelta(days=1)
    p = d - timedelta(days=1)
    return (int(datetime(p.year, p.month, p.day, 18, tzinfo=NY).timestamp()),
            int(datetime(d.year, d.month, d.day, tzinfo=NY).timestamp()))


def ctx_from_minutes(m: Minutes, now: int, gap: float = 0.0) -> MarketContext:
    """What the live feed would hand over at `now`: futures 5m/15m/1h/4h/1d (each with a forming last candle,
    finished minutes only) over the live look-back ranges, futures_last and futures_gap."""
    ctx = MarketContext(generated_at=datetime.fromtimestamp(now, timezone.utc), analysis_tf="15m", futures_gap=gap)
    sets = {"5m": (300, 5 * 288), "15m": (900, 5 * 96), "1h": (3600, 90 * 24), "4h": (14400, 90 * 6)}
    for tf, (sec, n) in sets.items():
        cs = resample(m, sec, now, n)
        b = now // sec * sec
        forming = _merge(m, b, now - 59, b)
        ctx.candles[f"fut_{tf}"] = CandleSet(key=f"fut_{tf}", timeframe=tf, kind="futures", source_label="test",
                                             candles=cs + ([forming] if forming else []),
                                             last_is_forming=forming is not None)
    daily = session_day_candles(m, now, 500)
    a, day_t = _session_start(now)
    forming = _merge(m, a, now - 59, day_t)
    ctx.candles["fut_1d"] = CandleSet(key="fut_1d", timeframe="1d", kind="futures", source_label="test",
                                      candles=daily + ([forming] if forming else []), last_is_forming=forming is not None)
    i = int(np.searchsorted(m.t, now - 60, side="right")) - 1
    if i >= 0:
        ctx.futures_last = float(m.c[i]) + gap
        ctx.futures_last_age_s = float(now - m.t[i] - 60)
    return ctx


class FakeModel:
    def __init__(self, p):
        self.p = np.asarray(p, dtype=float)
        self.seen = None

    def predict_proba(self, ds, idx):
        self.seen = ds.X[np.asarray(idx)].copy()
        return np.tile(self.p, (len(np.asarray(idx)), 1))


class FakeStacker:
    def __init__(self, p):
        self.p = np.asarray(p, dtype=float)
        self.got = None

    def predict_proba(self, ds, idx, p):
        self.got = np.asarray(p)
        return np.tile(self.p, (len(np.asarray(idx)), 1))


class FakeKNN:
    """Every live row maps to the origin, so neighbour i of the table below is at distance i."""

    def _space(self, ds, idx):
        return np.zeros((len(np.asarray(idx)), 2))


def fake_art(**kw) -> Artifacts:
    n = 10
    t0 = T - 400 * 86400
    meta = {"t": t0 + 30 * 86400 * np.arange(n), "kind": np.array(["CPI"] * 6 + ["NFP"] * 4),
            "z": np.array([1.2, np.nan, -0.4, 2.0, 0.1, -1.5, 0.3, np.nan, 1.1, -0.2]),
            "move60": np.array([4.0, -1.0, 0.5, 6.0, -3.0, -5.0, 2.0, 0.2, 3.0, -2.5]),
            "atr15": np.full(n, 2.0)}
    base = dict(primary=FakeModel([0.2, 0.3, 0.5]), primary_name="Fake", stacker=FakeStacker([0.1, 0.2, 0.7]),
                technical=FakeModel([0.3, 0.4, 0.3]), temperature=1.5,
                vol_table={("CPI", False): 1.5, ("CPI", True): 2.5, ("NFP", False): 1.2, ("NFP", True): 2.0},
                vol_kind={"CPI": 1.8, "NFP": 1.4}, vol_overall=1.6, stats_rows=[],
                neighbours_X=np.arange(n, dtype=float)[:, None] * np.array([[1.0, 0.0]]), neighbours_meta=meta,
                uncertain_max_p=0.45, uncertain_bhatt=1e9, m5_range_p99=2.5, go_live=False,
                trained_through="2026-08-14", version="test", knn=FakeKNN(), neighbour_k=7)
    base.update(kw)
    return Artifacts(**base)


CPI_EV = {"t": T, "name": "CPI (inflation)", "kind": "CPI"}


@pytest.fixture(scope="module")
def walk() -> Minutes:
    return _walk(1, T + 6 * 3600)


def _intel(m, now, art=None, events=(CPI_EV,), fetch=False, **kw):
    return live.build_intel(ctx_from_minutes(m, now), now, fake_art() if art is None else art, fetch=fetch,
                            events=list(events), **kw)


# ---------------------------------------------------------------- kind_of

KNOWN_TITLES = {
    # official kinds / names (core.news.official, core.newsintel.calendar)
    "CPI": "CPI", "CPI (inflation)": "CPI", "NFP": "NFP", "Jobs report (NFP)": "NFP", "FOMC": "FOMC",
    "Fed decision (FOMC)": "FOMC", "FOMC Decision": "FOMC", "PCE": "PCE", "PPI": "PPI", "GDP": "GDP",
    "GDP (advance)": "GDP", "RETAIL": "RETAIL", "CLAIMS": "CLAIMS", "Jobless Claims": "CLAIMS",
    # ForexFactory titles
    "CPI m/m": "CPI", "Core CPI m/m": "CPI", "CPI y/y": "CPI", "Core PCE Price Index m/m": "PCE",
    "PPI m/m": "PPI", "Core PPI m/m": "PPI", "Non-Farm Employment Change": "NFP", "Advance GDP q/q": "GDP",
    "Retail Sales m/m": "RETAIL", "Core Retail Sales m/m": "RETAIL", "Unemployment Claims": "CLAIMS",
    "Federal Funds Rate": "FOMC", "FOMC Statement": "FOMC",
    # deliberately no forecast: not the release the models were trained on
    "FOMC Press Conference": None, "FOMC Meeting Minutes": None, "Prelim GDP q/q": None, "Final GDP q/q": None,
    "ADP Non-Farm Employment Change": None, "Average Hourly Earnings m/m": None, "Unemployment Rate": None,
    "Congressional Elections": None, "Fed Chair Powell Speaks": None, "ISM Manufacturing PMI": None,
    "ISM Services PMI": None, "JOLTS Job Openings": None, "Prelim UoM Consumer Sentiment": None, "": None,
}


def test_kind_of_mapping():
    for title, kind in KNOWN_TITLES.items():
        assert live.kind_of(title) == kind, title


def test_every_high_impact_usd_title_on_disk_is_classified():
    """Every High-impact title the app has seen (data/news_events.json, data/news_week.json) is listed above."""
    titles = set()
    ev, wk = ROOT / "data" / "news_events.json", ROOT / "data" / "news_week.json"
    if ev.exists():
        titles |= {e["name"] for e in json.loads(ev.read_text()) if e.get("kind") == "FEED"}
    if wk.exists():
        titles |= {e["name"] for e in json.loads(wk.read_text())["week"] if e.get("impact") == "High"}
    if not titles:
        pytest.skip("no calendar files on disk")
    missing = sorted(titles - set(KNOWN_TITLES))
    assert not missing, f"classify these ForexFactory titles in KNOWN_TITLES: {missing}"


# ---------------------------------------------------------------- phase and event choice

def test_phase_windows(walk):
    assert _intel(walk, T - 23 * 3600).phase == "pre"
    post = _intel(walk, T + 179 * 60)
    assert post.phase == "post" and post.event["kind"] == "CPI" and post.event["t"] == T
    far = _intel(walk, T - 25 * 3600)
    assert far.phase == "none" and far.event is None and far.expected_move is None and far.probs is None
    assert _intel(walk, T + 181 * 60).phase == "none"


def test_priority_and_others(walk):
    events = [{"t": T, "name": "Unemployment Claims", "kind": "FEED"}, CPI_EV]
    it = _intel(walk, T - 3600, events=events)
    assert it.event["kind"] == "CPI"
    assert it.others == ["Jobless Claims"]
    assert it.features["n_releases"] == 2.0
    assert it.features["kind_CPI"] == 1.0 and it.features["kind_CLAIMS"] == 0.0


def test_post_event_beats_later_pre_event(walk):
    """CPI released 30 min ago and FOMC later the same day: the CPI reaction is the one shown."""
    fomc = {"t": T + 5 * 3600 + 1800, "name": "Fed decision (FOMC)", "kind": "FOMC"}
    it = _intel(walk, T + 1800, events=[CPI_EV, fomc])
    assert it.phase == "post" and it.event["kind"] == "CPI"
    assert any("FOMC" in n for n in it.notes)


def test_unknown_feed_title(walk):
    ev = [{"t": T, "name": "Congressional Elections", "kind": "FEED"}]
    it = _intel(walk, T - 2 * 3600, events=ev)
    assert it.phase == "none" and it.event is None
    assert it.expected_move is None and it.probs is None
    assert any("Congressional Elections" in n for n in it.notes)


def test_unknown_title_next_to_known_release_is_listed(walk):
    ev = [CPI_EV, {"t": T, "name": "Fed Chair Powell Speaks", "kind": "FEED"}]
    it = _intel(walk, T - 3600, events=ev)
    assert it.event["kind"] == "CPI" and it.others == ["Fed Chair Powell Speaks"]


# ---------------------------------------------------------------- surprise (FRED)

def _boom(series):
    raise RuntimeError(f"FRED request for {series} failed: ConnectError")


def test_no_fred(walk):
    it = _intel(walk, T + 20 * 60, fetch=_boom)
    assert it.phase == "post" and it.surprise_z is None
    assert it.features["z_missing"] == 1.0 and it.features["z"] == 0.0
    assert "Actual not published yet" in it.notes
    assert it.expected_move is not None  # still sized from the small-surprise bucket


def test_fetch_off_and_pre_phase_never_call_fred(walk):
    calls = []

    def spy(series):
        calls.append(series)
        raise AssertionError("must not be called")

    assert _intel(walk, T - 3600, fetch=spy).surprise_z is None  # before the release: nothing to look up
    assert calls == []
    it = _intel(walk, T + 600, fetch=False)
    assert it.surprise_z is None and it.features["z_missing"] == 1.0


def _vintages(values, first_obs="2020-01-01", day=12) -> list[dict]:
    """Monthly vintage rows: obs month k first published on `day` of month k+1 and never revised."""
    rows = []
    y0, m0 = map(int, first_obs[:7].split("-"))
    for k, v in enumerate(values):
        y, mo = divmod(y0 * 12 + m0 - 1 + k, 12)
        ry, rm = divmod(y * 12 + mo + 1, 12)
        rows.append({"date": f"{y:04d}-{mo + 1:02d}-01", "realtime_start": f"{ry:04d}-{rm + 1:02d}-{day:02d}",
                     "realtime_end": "9999-12-31", "value": f"{v:.4f}"})
    return rows


def test_post_surprise_from_vintages(walk):
    """After the release, z is the first release of that day scored by `expectations` on the whole history."""
    rng = np.random.default_rng(5)
    level = 250.0 * np.cumprod(1 + rng.normal(0.002, 0.001, 50))
    level[-1] = level[-2] * 1.012  # a hot print: far above the AR(1) expectation
    # obs 2020-01 .. 2024-02; the last one (Feb 2024) is first published 2024-03-12, the CPI day of T
    head, core = _vintages(level), _vintages(level * 1.1)
    assert head[-1]["realtime_start"] == "2024-03-12"
    series = {"CPIAUCSL": head, "CPILFESL": core}
    it = _intel(walk, T + 20 * 60, fetch=lambda s: series[s])
    rels = first_releases(head, "pct_mom")
    want = expectations(rels, 1)[-1].z
    assert want is not None and want > 1
    assert it.surprise_z == pytest.approx(want, abs=1e-12)
    assert it.features["z"] == pytest.approx(want) and it.features["abs_z"] == pytest.approx(abs(want))
    assert it.features["z_missing"] == 0.0
    want_core = expectations(first_releases(core, "pct_mom"), 1)[-1].z
    assert it.features["core_z"] == pytest.approx(want_core)


def test_fomc_post_has_no_surprise_lookup(walk):
    fomc = {"t": T, "name": "Fed decision (FOMC)", "kind": "FOMC"}
    it = _intel(walk, T + 600, events=[fomc], fetch=_boom)
    assert it.phase == "post" and it.surprise_z is None and it.features["z_missing"] == 1.0
    assert "Actual not published yet" not in it.notes


# ---------------------------------------------------------------- candles missing / short / stale

def test_short_candles():
    m = _walk(3, T + 3600, days=1, start=T - 10 * 3600)  # 40 15m candles before T
    it = _intel(m, T - 1800)
    assert it.phase == "pre" and it.event["kind"] == "CPI"
    assert it.expected_move is None and it.probs is None and it.expected_range is None
    assert any("15-minute candles" in n for n in it.notes)


def test_market_closed_no_fresh_candles():
    """Sunday morning before a Monday release: the newest candle is Friday's, so no move is sized."""
    mon = int(datetime(2024, 3, 11, 8, 30, tzinfo=NY).timestamp())
    fri_close = int(datetime(2024, 3, 8, 17, 0, tzinfo=NY).timestamp())
    m = _walk(4, fri_close, days=30)
    now = mon - 20 * 3600
    it = live.build_intel(ctx_from_minutes(m, now), now, fake_art(), fetch=False,
                          events=[{"t": mon, "name": "Retail Sales m/m", "kind": "FEED"}])
    assert it.phase == "pre" and it.event["kind"] == "RETAIL"
    assert it.expected_move is None and it.probs is None
    assert any("closed" in n for n in it.notes)


def test_empty_context_never_raises():
    ctx = MarketContext(generated_at=datetime.fromtimestamp(T, timezone.utc), analysis_tf="15m")
    it = live.build_intel(ctx, T - 3600, fake_art(), fetch=_boom, events=[CPI_EV])
    assert it.phase == "pre" and it.expected_move is None and it.probs is None and it.m5_ratio is None
    it = live.build_intel(ctx, T + 600, fake_art(), fetch=_boom, events=[CPI_EV])
    assert it.phase == "post" and it.surprise_z is None


def test_no_artifacts(walk):
    it = live.build_intel(ctx_from_minutes(walk, T - 3600), T - 3600, None, fetch=False, events=[CPI_EV])
    assert it.phase == "pre" and it.event["kind"] == "CPI"
    assert it.probs is None and it.expected_move is None and it.similar == [] and not it.go_live
    assert any("not built yet" in n for n in it.notes)


# ---------------------------------------------------------------- expected move, chances, similar

def test_expected_move(walk):
    art = fake_art()
    now = T - 3600
    it = _intel(walk, now, art=art)
    a15 = atr(resample(walk, 900, now, 60), 14)[-1]
    assert it.features["atr15"] == pytest.approx(a15, abs=1e-9)
    assert it.expected_move == pytest.approx(art.vol_table[("CPI", False)] * a15)  # pre: z unknown -> small bucket
    price = round(ctx_from_minutes(walk, now).futures_last, 2)  # MarketContext.sp rounds spot levels to cents
    lo, hi = it.expected_range
    assert lo == pytest.approx(price - it.expected_move) and hi == pytest.approx(price + it.expected_move)
    # the bucket rule itself: (kind, |z|>=1) -> kind -> overall
    assert live.expected_ratio(art, "CPI", 1.3) == 2.5
    assert live.expected_ratio(art, "CPI", -1.0) == 2.5
    assert live.expected_ratio(art, "CPI", 0.7) == 1.5
    assert live.expected_ratio(art, "CPI", None) == 1.5
    assert live.expected_ratio(fake_art(vol_table={}), "CPI", 2.0) == 1.8
    assert live.expected_ratio(art, "GDP", 2.0) == 1.6


def test_expected_range_uses_spot_levels(walk):
    """Futures run above spot: the range is centred on the spot price (futures_last - gap)."""
    now = T - 3600
    m = walk
    ctx = ctx_from_minutes(m, now, gap=12.0)
    it = live.build_intel(ctx, now, fake_art(), fetch=False, events=[CPI_EV])
    spot = round(ctx.futures_last - 12.0, 2)
    assert sum(it.expected_range) / 2 == pytest.approx(spot)


def test_probs_use_temperature_scaled_primary(walk):
    art = fake_art()
    it = _intel(walk, T - 3600, art=art)
    assert it.probs == pytest.approx({"down": 0.1, "side": 0.2, "up": 0.7})
    assert it.tech_probs == pytest.approx({"down": 0.3, "side": 0.4, "up": 0.3})
    np.testing.assert_allclose(art.stacker.got, apply_temperature(np.array([[0.2, 0.3, 0.5]]), 1.5))
    # the models saw exactly the live row
    np.testing.assert_allclose(art.primary.seen[0], [it.features[n] for n in FEATURE_NAMES])


def test_similar_and_coherence(walk):
    it = _intel(walk, T - 3600)
    assert 1 <= len(it.similar) <= 8
    first = it.similar[0]  # neighbours_X row 0 is nearest
    assert first["kind"] == "CPI" and first["move60"] == 4.0 and first["z"] == 1.2 and first["label"] == "up"
    assert it.similar[1]["z"] is None and it.similar[1]["label"] == "down"  # -1.0 = 0.5 x atr15
    assert it.similar[2]["label"] == "side"  # |0.5| < 0.5 x atr15 (2.0)
    assert first["date"] == datetime.fromtimestamp(T - 400 * 86400, NY).strftime("%Y-%m-%d")
    assert it.coherence is not None and it.coherence >= 0


def test_uncertain_flag(walk):
    # confident and coherent -> not uncertain
    ok = _intel(walk, T - 3600, art=fake_art(stacker=FakeStacker([0.05, 0.05, 0.9]), uncertain_max_p=0.5))
    assert not ok.uncertain
    # max chance below the threshold
    low = _intel(walk, T - 3600, art=fake_art(stacker=FakeStacker([0.3, 0.32, 0.38]), uncertain_max_p=0.45))
    assert low.uncertain
    # neighbours' reactions less alike than the threshold
    inc = _intel(walk, T - 3600, art=fake_art(stacker=FakeStacker([0.05, 0.05, 0.9]), uncertain_max_p=0.5,
                                              uncertain_bhatt=-1.0))
    assert inc.uncertain
    assert not _intel(walk, T - 25 * 3600).uncertain  # nothing to be uncertain about


def test_coherence_matches_export_definition():
    """Bhattacharyya between the k neighbours' move60/atr15 and all same-kind rows', as export.oos_bhattacharyya."""
    from core.newsintel.ml.stats import bhattacharyya
    art = fake_art()
    meta = art.neighbours_meta
    ratio = meta["move60"] / meta["atr15"]
    nb = np.arange(art.neighbour_k)
    want = bhattacharyya(ratio[nb], ratio[meta["kind"] == "CPI"])
    got, sim = live.neighbours(art, np.zeros(len(FEATURE_NAMES)), "CPI")
    assert got == pytest.approx(want)
    assert [s["move60"] for s in sim] == list(meta["move60"][:8])


# ---------------------------------------------------------------- M5 ratio

def test_m5_ratio():
    cs = [Candle(t=i * 300, o=100, h=101, l=99, c=100) for i in range(30)]
    cs.append(Candle(t=30 * 300, o=100, h=106, l=100, c=105))
    want = 6.0 / atr(cs, 14)[-1]
    assert live.m5_ratio(cs) == pytest.approx(want)
    assert live.m5_ratio(cs[:10]) is None
    assert live.m5_ratio([]) is None


def test_intel_m5_ratio_uses_last_completed_bar(walk):
    now = T - 3600 + 130  # inside a forming 5m bar
    it = _intel(walk, now)
    done = resample(walk, 300, now, 5 * 288)
    assert it.m5_ratio == pytest.approx((done[-1].h - done[-1].l) / atr(done, 14)[-1])


# ---------------------------------------------------------------- feature parity

PARITY_KEYS = ("atr15", "atr1h", "pre_range_atr15", "trend_score")


def _assert_parity(m: Minutes, t: int, now: int):
    row = live.live_features(ctx_from_minutes(m, now), t, None, None, None, "CPI")
    f = features(m, t, None)
    want = {"atr15": f.atr15, "atr1h": f.atr1h, "pre_range_atr15": f.pre_range / f.atr15,
            "trend_score": f.trend_score}
    for k in PARITY_KEYS:
        assert want[k] is not None
        assert abs(row[COL[k]] - want[k]) < 1e-6, (k, t, row[COL[k]], want[k])
    return row


def test_feature_parity():
    m = _walk(7, T + 4 * 3600, days=130)
    for t in (T, T - 86400 + 5 * 3600, T - 3 * 86400 + 1800):
        row = _assert_parity(m, t, t + 47 * 60)  # the live call comes 47 min after the release
        assert row[COL["overlap"]] == float(8 <= datetime.fromtimestamp(t, NY).hour <= 11)


def test_features_ignore_candles_after_release():
    m = _walk(8, T + 4 * 3600, days=60)
    base = live.live_features(ctx_from_minutes(m, T + 3600), T, None, None, None, "CPI")
    late = m.t + 60 > T
    h, l = m.h.copy(), m.l.copy()
    h[late] += 500.0
    l[late] -= 500.0
    again = live.live_features(ctx_from_minutes(Minutes(m.t, m.o, h, l, m.c), T + 3600), T, None, None, None, "CPI")
    np.testing.assert_array_equal(base, again)


def _real_release_times(n: int = 24) -> list[int]:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        ts = [r[0] for r in con.execute(
            "SELECT DISTINCT e.t FROM events e JOIN reactions r ON r.t = e.t "
            "WHERE e.t >= ? AND r.incomplete = 0 ORDER BY e.t",
            (int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp()),))]
    finally:
        con.close()
    pick = np.linspace(0, len(ts) - 1, n).round().astype(int)
    return [ts[i] for i in sorted(set(pick))]


@pytest.mark.skipif(not (NPZ.exists() and DB.exists()), reason="real 1-minute backup or news_intel.db not present")
def test_real_feature_parity():
    z = np.load(NPZ)
    m = Minutes(z["t"], z["o"], z["h"], z["l"], z["c"])
    times = _real_release_times()
    assert len(times) >= 20
    years = {datetime.fromtimestamp(t, NY).year for t in times}
    assert {2022, 2023, 2024, 2025, 2026} <= years
    for t in times:
        _assert_parity(m, t, t + 47 * 60)


# ---------------------------------------------------------------- real FRED dry run

def _fred_key() -> str | None:
    from core.env import load_env
    load_env()
    return os.environ.get("FRED_API_KEY") or None


@pytest.mark.skipif(not DB.exists(), reason="news_intel.db not present")
def test_real_fred_surprise_matches_stored():
    """For the last 3 CPI, NFP and PCE releases in the database, the live post-release z equals the stored one."""
    if not _fred_key():
        pytest.skip("FRED_API_KEY not set: live FRED dry run skipped")
    from core.newsintel import fred
    key = _fred_key()
    rows: dict[str, list] = {}

    def download(series):  # the live path's download, without touching the on-disk cache
        if series not in rows:
            rows[series] = fred._download(series, key)
        return rows[series]

    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        cases = []
        for kind in ("CPI", "NFP", "PCE"):
            cases += con.execute("SELECT kind, t, surprise_z FROM events WHERE kind = ? ORDER BY t DESC LIMIT 3",
                                 (kind,)).fetchall()
    finally:
        con.close()
    try:
        download("CPIAUCSL")
    except RuntimeError as e:
        pytest.skip(f"FRED unreachable: {e}")
    for kind, t, stored in cases:
        z, _core, _why = live.surprise(kind, t, download)
        if stored is None:
            assert z is None, (kind, t)
        else:
            assert z is not None and abs(z - stored) < 1e-9, (kind, t, z, stored)
