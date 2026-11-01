"""Live news intelligence: the current market context + the economic calendar + the saved news models -> `Intel`.

Phase: "pre" up to 24 h before a release, "post" from the release to 180 min after it, otherwise "none".
When several releases share a time, the highest-priority kind (ml.data.PRIORITY) is the one described and the
others are listed by name. ForexFactory titles that do not map to a known kind still block trading elsewhere
(core.news), but get no forecast here.

The feature row follows core/newsintel/features.py + ml/data.py exactly, with the live candle sets standing in for
the 1-minute history: only candles finished by the cut-off time are used (the release time after it, the current
time before it). The expected move is the typical first-hour move for this kind of release (median
|move60| / ATR15 of past releases of the kind, times the current 15-minute ATR) - volatility scaling, not a news
forecast. Chances are advisory (stacker on the temperature-scaled primary model).

Data lag: the live 5m/15m/1h/4h/1d candles are gold FUTURES from Yahoo, delayed about 10 minutes. `m5_ratio` and the
pre-release features therefore describe the market as of ~10 minutes ago, and any gate built on them (abnormal
volatility) fires about 10-15 minutes late. Ranges and ATRs do not depend on the futures-spot gap; price levels
(the expected range) are converted to spot with `ctx.futures_gap`.

Weekly jobless claims are not in the live calendar feed (medium impact) but are in the training calendar, so they
are counted from the FRED ICSA release days (cached copy; past days only, so no look-ahead), falling back to
"every Thursday 08:30" when the cache does not cover the date.

The FRED lookup after a release can take a long time; the app calls `build_intel_async`, which never waits for it.

Nothing here raises on missing data: short or stale candles, a FRED outage, missing models or an unknown title
give an `Intel` with a plain note instead.
"""
from __future__ import annotations

import asyncio
import re
from bisect import bisect_right
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

import numpy as np

from agents.chief import TFS
from core import news
from core.indicators import atr
from core.models import Candle, CandleSet, MarketContext
from core.newsintel import fred
from core.newsintel.bars import NY
from core.newsintel.calendar import RELEASES
from core.newsintel.features import MIN_CANDLES, N_TREND
from core.newsintel.fred import first_releases
from core.newsintel.ml.data import CLASSES, CORE_SERIES, FEATURE_NAMES, HOURS_CAP, PRIORITY, Dataset
from core.newsintel.ml.metrics import apply_temperature
from core.newsintel.ml.stack import Z_EDGE
from core.newsintel.ml.stats import bhattacharyya
from core.newsintel.reactions import SIDE_ATR
from core.newsintel.surprise import expectations
from core.structure import tf_bias

PRE_S = 24 * 3600          # "pre" window before a release
POST_S = 180 * 60          # "post" window after it
STALE_S = 3600             # newest finished 15m candle older than this (vs the cut-off) = market closed / feed behind
N_SIMILAR = 8
FRED_RETRY_S = 10 * 60     # after a failed or empty FRED lookup, wait this long before asking again
_SEC = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
NO_MODELS = "News models not built yet (run python -m core.newsintel.ml --export)"
NOT_PUBLISHED = "Actual not published yet"
DISPLAY = {k: v["name"] for k, v in RELEASES.items()} | {"FOMC": "FOMC Decision"}

Fetch = Callable[[str], list]  # series id -> FRED vintage rows (as fred.fetch_vintages returns them)


@dataclass
class Intel:
    phase: str                                  # "pre" | "post" | "none"
    event: dict | None = None                   # {kind, name, t}
    others: list[str] = field(default_factory=list)
    expected_move: float | None = None          # dollars, first 60 min after the release (typical, ATR-scaled)
    expected_range: tuple[float, float] | None = None
    probs: dict[str, float] | None = None       # down / side / up, advisory
    tech_probs: dict | None = None
    surprise_z: float | None = None
    similar: list[dict] = field(default_factory=list)
    coherence: float | None = None              # Bhattacharyya distance: neighbours' reactions vs the kind's
    uncertain: bool = False
    notes: list[str] = field(default_factory=list)
    go_live: bool = False
    trained_through: str | None = None
    m5_ratio: float | None = None               # last finished 5m range / 5m ATR(14), see m5_ratio()
    features: dict[str, float] | None = None    # the model row, FEATURE_NAMES -> value


# ---------------------------------------------------------------- calendar

_SKIP = re.compile(r"press conference|minutes|speaks|speech|testif|\bADP\b", re.I)
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bPCE\b", re.I), "PCE"),
    (re.compile(r"\bPPI\b", re.I), "PPI"),
    (re.compile(r"\bCPI\b", re.I), "CPI"),
    (re.compile(r"non-farm|\bNFP\b", re.I), "NFP"),
    (re.compile(r"^\s*GDP(\s*\(advance\))?\s*$|\badvance GDP\b", re.I), "GDP"),  # advance estimate only
    (re.compile(r"retail sales", re.I), "RETAIL"),
    (re.compile(r"unemployment claims|jobless claims", re.I), "CLAIMS"),
    (re.compile(r"\bFOMC\b|federal funds rate", re.I), "FOMC"),
]


def kind_of(name: str) -> str | None:
    """Release kind of an official kind/name or a ForexFactory title; None when the models do not know it.

    FOMC press conferences / minutes, Fed speeches, ADP, preliminary/final GDP, average hourly earnings and the
    unemployment rate deliberately map to None: they are not the release the models were trained on.
    """
    s = (name or "").strip()
    if s.upper() in PRIORITY:
        return s.upper()
    if not s or _SKIP.search(s):
        return None
    for rx, kind in _RULES:
        if rx.search(s):
            return kind
    return None


def _kind(e: dict) -> str | None:
    return e["kind"] if e.get("kind") in PRIORITY else kind_of(e.get("name", ""))


def _name(e: dict, kind: str | None) -> str:
    return DISPLAY.get(kind, e.get("name", "")) if kind else e.get("name", "")


def _ny(t: int) -> datetime:
    return datetime.fromtimestamp(t, NY)


_claims_memo: dict = {"mtime": None, "days": None}


def _claims_days() -> list[str] | None:
    """Sorted New York days on which ICSA (weekly claims) was first published, from the cached FRED copy."""
    f = fred.CACHE / "ICSA.json"
    try:
        mt = f.stat().st_mtime
        if _claims_memo["mtime"] != mt:
            rels = first_releases(fred.fetch_vintages("ICSA", offline=True), "level")
            _claims_memo.update(mtime=mt, days=sorted({r.release_date for r in rels}))
        return _claims_memo["days"]
    except Exception:  # noqa: BLE001 - no cache: Thursday rule
        return None


def _claims_ts(day: str) -> int:
    y, m, d = map(int, day.split("-"))
    return int(datetime(y, m, d, 8, 30, tzinfo=NY).timestamp())


def _claims_at(t: int) -> bool:
    """Weekly jobless claims released at t (08:30 New York)? FRED release days when the cache covers the date,
    else every Thursday 08:30."""
    d = _ny(t)
    if (d.hour, d.minute) != (8, 30):
        return False
    day, days = d.strftime("%Y-%m-%d"), _claims_days()
    if days and day <= days[-1]:
        return day in set(days)
    return d.weekday() == 3


def _last_claims_before(t: int) -> int:
    days = _claims_days()
    if days:
        i = bisect_right(days, _ny(t).strftime("%Y-%m-%d"))
        past = [x for x in (_claims_ts(dd) for dd in days[max(0, i - 2):i]) if x < t]
        # the cache covers t (a later release is known) or saw a release within a week: trust it, even across a
        # gap such as the 2025 shutdown; otherwise it is simply out of date and the Thursday rule fills in
        if past and (i < len(days) or t - past[-1] <= 8 * 86400):
            return past[-1]
    d = _ny(t).date()
    for back in range(0, 8):
        x = d - timedelta(days=back)
        ts = int(datetime(x.year, x.month, x.day, 8, 30, tzinfo=NY).timestamp())
        if x.weekday() == 3 and ts < t:
            return ts
    return t - 7 * 86400  # unreachable: some Thursday lies in the last 8 days


def _prev_release(events: list[dict], t: int) -> int:
    """The previous release (any known kind) before t; weekly claims count, as in the training calendar."""
    prev = [int(e["t"]) for e in events if int(e["t"]) < t and _kind(e) is not None]
    return max(prev + [_last_claims_before(t)])


# ---------------------------------------------------------------- candles -> features

def _done(cs: CandleSet | None, sec: int, cut: int) -> list[Candle]:
    """Finished candles (not the forming one) that ended by `cut`."""
    if cs is None:
        return []
    return [c for c in cs.closed() if c.t + sec <= cut]


def _done_daily(cs: CandleSet | None, cut: int) -> list[Candle]:
    """Finished gold sessions: a daily candle dated D (New York) ends at 17:00 New York on D."""
    if cs is None:
        return []
    out = []
    for c in cs.closed():
        d = _ny(c.t).date()
        if int(datetime(d.year, d.month, d.day, 17, tzinfo=NY).timestamp()) <= cut:
            out.append(c)
    return out


def _m5_set(ctx: MarketContext) -> CandleSet | None:
    """5-minute candles with a real high/low: futures first (ranges do not depend on the futures-spot gap; the
    spot candles are built from sparse price samples and understate the range), else spot."""
    for key in ("fut_5m", "spot_5m"):
        cs = ctx.candles.get(key)
        if cs and cs.candles:
            return cs
    return None


def _atr_last(cs: list[Candle]) -> float | None:
    return atr(cs, 14)[-1] if cs else None


def _raw(ctx: MarketContext, cut: int) -> dict:
    """atr15, atr1h, pre_range, trend_score as of `cut` (features.py definitions), plus candle health."""
    c15 = _done(ctx.struct("15m"), 900, cut)
    m5 = [c for c in _done(_m5_set(ctx), 300, cut) if c.t >= cut - 3600]
    total, used = 0.0, False
    for key, _name_, mult, w in TFS:
        cs = _done_daily(ctx.struct("1d"), cut) if key == "1d" else _done(ctx.struct(key), _SEC[key], cut)
        cs = cs[-N_TREND:]
        if len(cs) < MIN_CANDLES:
            continue
        total += w * max(-1.0, min(1.0, tf_bias(cs, mult)["score"] / 2.5))
        used = True
    return {"atr15": _atr_last(c15[-60:]), "atr1h": _atr_last(_done(ctx.struct("1h"), 3600, cut)[-60:]),
            "pre_range": max(c.h for c in m5) - min(c.l for c in m5) if m5 else None,
            "trend_score": total if used else None,
            "n15": len(c15), "last15_end": c15[-1].t + 900 if c15 else None}


def _num(v) -> float:
    return 0.0 if v is None else float(v)


def _row(raw: dict, t: int, prev_t: int | None, z: float | None, core_z: float | None, kind: str,
         n_releases: int) -> np.ndarray:
    """One row in FEATURE_NAMES order, missing values handled exactly as ml.data.load does."""
    a15, pre = _num(raw["atr15"]), _num(raw["pre_range"])
    hours = None if prev_t is None else (t - prev_t) / 3600
    onehot = [1.0 if kind == k else 0.0 for k in PRIORITY]
    return np.array([_num(z), _num(core_z), abs(_num(z)), 1.0 if z is None else 0.0, *onehot,
                     a15, _num(raw["atr1h"]), pre / a15 if a15 > 0 else 0.0, _num(raw["trend_score"]),
                     min(_num(hours), HOURS_CAP), float(8 <= _ny(t).hour <= 11), float(n_releases)],
                    dtype=np.float64)


def live_features(ctx: MarketContext, t: int, prev_t: int | None, z: float | None, core_z: float | None,
                  kind: str, *, asof: int | None = None, n_releases: int = 1) -> np.ndarray:
    """The model row for a release at t, from the live candle sets.

    Candles count only if finished by `asof` (default t: the moment of the release, as in features.py; before a
    release the caller passes the current time). Release-time facts (overlap, hours since the previous release)
    always use t.
    """
    return _row(_raw(ctx, t if asof is None else asof), t, prev_t, z, core_z, kind, n_releases)


def m5_ratio(candles: list[Candle]) -> float | None:
    """(high - low of the last candle) / ATR(14) over the candles including it; the caller passes only finished
    5-minute candles. None with 14 or fewer candles or a zero ATR."""
    if len(candles) <= 14:
        return None
    a = atr(candles, 14)[-1]
    if not a or a <= 0:
        return None
    return (candles[-1].h - candles[-1].l) / a


# ---------------------------------------------------------------- surprise (FRED)

def _series_z(spec: tuple, day: str, get: Fetch) -> float | None:
    """z of the newest observation first published on `day`, scored on the whole first-release history."""
    sid, transform, sign, _headline = spec
    rels = first_releases(get(sid), transform)
    hits = [(r.obs_date, s.z) for r, s in zip(rels, expectations(rels, sign)) if r.release_date == day]
    return max(hits)[1] if hits else None


def surprise(kind: str, t: int, get: Fetch) -> tuple[float | None, float | None, str | None]:
    """(headline z, core z, reason when missing) for the release of `kind` at t, computed as calendar.build_events
    does. `get` errors propagate to the caller."""
    spec = RELEASES.get(kind)
    if spec is None:
        return None, None, None
    day = _ny(t).strftime("%Y-%m-%d")
    head = next(s for s in spec["series"] if s[3])
    z = _series_z(head, day, get)
    core_z = None
    core_id = CORE_SERIES.get(kind)
    if z is not None and core_id:
        core = next((s for s in spec["series"] if s[0] == core_id), None)
        core_z = _series_z(core, day, get) if core else None
    return z, core_z, None if z is not None else NOT_PUBLISHED


_found: dict[tuple[str, int], tuple[float, float | None]] = {}
_tried: dict[tuple[str, int], float] = {}


def _cached_rows(sid: str) -> list:
    return fred.fetch_vintages(sid, offline=True)


def _cached_surprise(kind: str, t: int) -> tuple[float | None, float | None, str | None]:
    """Remembered or on-disk FRED copy only: never downloads."""
    if (kind, t) in _found:
        z, core = _found[(kind, t)]
        return z, core, None
    try:
        z, core, why = surprise(kind, t, _cached_rows)
    except Exception:  # noqa: BLE001 - no cached copy yet
        return None, None, NOT_PUBLISHED
    if z is not None:
        _found[(kind, t)] = (z, core)
    return z, core, why


def _default_surprise(kind: str, t: int) -> tuple[float | None, float | None, str | None]:
    """The on-disk FRED copy first; if the release is not in it, ask FRED (at most every FRED_RETRY_S)."""
    key = (kind, t)
    if key in _found:
        z, core = _found[key]
        return z, core, None
    try:
        z, core, why = surprise(kind, t, _cached_rows)
    except Exception:  # noqa: BLE001 - no cached copy yet
        z, core, why = None, None, NOT_PUBLISHED
    if z is None and time.time() - _tried.get(key, 0.0) >= FRED_RETRY_S:
        _tried[key] = time.time()
        z, core, why = surprise(kind, t, fred.download)
    if z is not None:
        _found[key] = (z, core)
    return z, core, why


def _lookup_surprise(kind: str, t: int, fetch) -> tuple[float | None, float | None, str | None]:
    if kind not in RELEASES:
        return None, None, None  # FOMC: no surprise score
    if fetch is False or fetch is None:
        return None, None, NOT_PUBLISHED
    try:
        if fetch == "cached":
            return _cached_surprise(kind, t)
        if callable(fetch):
            return surprise(kind, t, fetch)
        return _default_surprise(kind, t)
    except Exception as e:  # noqa: BLE001 - FRED down / no key / bad data: surprise unknown, never an error
        print(f"[newsintel] surprise for {kind} unavailable: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        return None, None, NOT_PUBLISHED


# ---------------------------------------------------------------- models

def expected_ratio(art, kind: str, z: float | None) -> float:
    """Median |move60|/ATR15 for (kind, |z| >= 1), falling back to the kind, then to all releases (stack.vol_forecast).
    A missing surprise counts as |z| < 1."""
    big = z is not None and abs(z) >= Z_EDGE
    r = art.vol_table.get((kind, big))
    if r is None:
        r = art.vol_kind.get(kind, art.vol_overall)
    return float(r)


def _one(row: np.ndarray, kind: str, t: int = 0) -> Dataset:
    return Dataset(t=np.array([t], dtype=np.int64), X=row.reshape(1, -1).astype(np.float64),
                   y=np.zeros(1, dtype=np.int64), y120=np.full(1, -1, dtype=np.int64), kind=np.array([kind]),
                   absmove60=np.zeros(1), atr15=np.array([row[FEATURE_NAMES.index("atr15")]]),
                   feature_names=list(FEATURE_NAMES), move60=np.zeros(1))


def _neighbour_atr(art) -> np.ndarray:
    meta = art.neighbours_meta
    if meta.get("atr15") is not None:
        return np.asarray(meta["atr15"], dtype=np.float64)
    # not stored: undo the KNN scaling of the atr15 column (kind columns are the only weighted ones)
    col = FEATURE_NAMES.index("atr15")
    sc = art.knn.scaler_
    return art.neighbours_X[:, col] * sc.scale_[col] + sc.mean_[col]


def _label(move: float, a: float) -> str | None:
    if not a or a <= 0:
        return None
    return "side" if abs(move) < SIDE_ATR * a else ("up" if move > 0 else "down")


def neighbours(art, row: np.ndarray, kind: str) -> tuple[float | None, list[dict]]:
    """(coherence, similar past releases) for a live row, as export.oos_bhattacharyya: the k nearest rows in the
    fitted KNN's space; coherence = Bhattacharyya distance between their move60/atr15 and all rows of the kind."""
    q = art.knn._space(_one(row, kind), [0])[0]
    order = np.argsort(np.linalg.norm(art.neighbours_X - q, axis=1), kind="stable")
    meta = art.neighbours_meta
    a = _neighbour_atr(art)
    move = np.asarray(meta["move60"], dtype=np.float64)
    ratio = np.where(a > 0, move / np.where(a > 0, a, 1.0), 0.0)
    same = np.asarray(meta["kind"]) == kind
    coh = float(bhattacharyya(ratio[order[:art.neighbour_k]], ratio[same])) if same.any() else None
    similar = []
    for i in order[:N_SIMILAR]:
        z = float(meta["z"][i])
        similar.append({"date": _ny(int(meta["t"][i])).strftime("%Y-%m-%d"), "kind": str(meta["kind"][i]),
                        "z": None if np.isnan(z) else z, "move60": float(move[i]), "label": _label(move[i], a[i])})
    return coh, similar


def _chances(art, row: np.ndarray, kind: str) -> tuple[dict, dict]:
    ds = _one(row, kind)
    p = apply_temperature(art.primary.predict_proba(ds, [0]), art.temperature)
    if art.stacker is not None:
        p = art.stacker.predict_proba(ds, [0], p)
    tech = art.technical.predict_proba(ds, [0])
    return ({c: float(p[0, i]) for i, c in enumerate(CLASSES)}, {c: float(tech[0, i]) for i, c in enumerate(CLASSES)})


def _price(ctx: MarketContext, c15: list[Candle]) -> float | None:
    """Spot price: live quote if fresh, else futures minus the gap, else the last 15m close minus the gap."""
    if ctx.spot is not None and not ctx.spot.stale:
        return ctx.spot.price
    if ctx.futures_last is not None:
        return ctx.sp(ctx.futures_last)
    return ctx.sp(c15[-1].c) if c15 else None


def _when(t: int, now: float) -> str:
    mins = round((t - now) / 60)
    if mins >= 0:
        return f"in {mins} min" if mins < 120 else f"in {mins / 60:.1f} h"
    return f"{-mins} min ago" if -mins < 120 else f"{-mins / 60:.1f} h ago"


# ---------------------------------------------------------------- build_intel

def build_intel(ctx: MarketContext, now: float, art, fetch=True, events: list[dict] | None = None) -> Intel:
    """The news picture at `now`. `fetch`: True = FRED (cached copy first), False = no lookup, or a callable
    series id -> vintage rows. `events` defaults to core.news.events()."""
    now_i = int(now)
    if events is None:
        try:
            events = news.events()
        except Exception as e:  # noqa: BLE001 - calendar unreadable: behave as "no news"
            print(f"[newsintel] calendar unavailable: {type(e).__name__}: {e}", file=sys.stderr)
            events = []
    intel = Intel(phase="none", go_live=bool(art.go_live) if art is not None else False,
                  trained_through=getattr(art, "trained_through", None) if art is not None else None)
    if art is None:
        intel.notes.append(NO_MODELS)

    m5 = _done(_m5_set(ctx), 300, now_i)
    if m5 and m5[-1].t + 300 >= now_i - STALE_S:
        intel.m5_ratio = m5_ratio(m5)

    # group calendar entries by release time; keep the ones in the pre/post windows
    groups: dict[int, list[tuple[dict, str | None]]] = {}
    for e in events:
        t = int(e["t"])
        if t - PRE_S < now_i <= t + POST_S:
            groups.setdefault(t, []).append((e, _kind(e)))
    known = {t: g for t, g in groups.items() if any(k for _e, k in g)}
    post = [t for t in known if t <= now_i]
    pre = [t for t in known if t > now_i]
    chosen = max(post) if post else (min(pre) if pre else None)

    for t in sorted(groups):
        if t == chosen:
            continue
        g = groups[t]
        names = list(dict.fromkeys(_name(e, k) for e, k in g))
        if t in known:
            intel.notes.append(f"Also on the calendar: {', '.join(names)} {_when(t, now)}.")
        else:
            intel.notes.append(f"{', '.join(names)} {_when(t, now)}: not a release the news models know, so no "
                               "forecast (the no-trade window still applies).")
    if chosen is None:
        if not groups:
            intel.notes.append("No major US release in the next 24 hours.")
        return intel

    g = sorted(known[chosen], key=lambda ek: PRIORITY.index(ek[1]) if ek[1] else len(PRIORITY))
    prim_e, kind = g[0]
    kinds = list(dict.fromkeys(k for _e, k in g if k))
    intel.phase = "post" if chosen <= now_i else "pre"
    intel.event = {"kind": kind, "name": _name(prim_e, kind), "t": chosen}
    others = [DISPLAY[k] for k in kinds[1:]] + [e.get("name", "") for e, k in g if not k]
    intel.others = list(dict.fromkeys(others))
    n_releases = len(kinds) + (1 if _claims_at(chosen) and "CLAIMS" not in kinds else 0)

    z = core_z = None
    if intel.phase == "post":
        z, core_z, why = _lookup_surprise(kind, chosen, fetch)
        intel.surprise_z = z
        if why:
            intel.notes.append(why)
    elif kind in RELEASES:
        intel.notes.append("Before the release the actual number is unknown, so the small-surprise case is used.")

    cut = min(now_i, chosen)
    raw = _raw(ctx, cut)
    row = _row(raw, chosen, _prev_release(events, chosen), z, core_z, kind, n_releases)
    intel.features = {n: float(v) for n, v in zip(FEATURE_NAMES, row)}

    ok = True
    if raw["n15"] < MIN_CANDLES:
        intel.notes.append(f"Only {raw['n15']} recent 15-minute candles (60 needed): typical move and chances "
                           "are not shown.")
        ok = False
    elif raw["last15_end"] < cut - STALE_S:
        hours = (cut - raw["last15_end"]) / 3600
        intel.notes.append(f"Market closed or price feed behind (newest 15-minute candle is {hours:.1f} h old): "
                           "typical move and chances are not shown.")
        ok = False
    elif not raw["atr15"] or raw["atr15"] <= 0:
        intel.notes.append("No 15-minute volatility reading: typical move and chances are not shown.")
        ok = False

    if art is None or not ok:
        intel.uncertain = True
        return intel

    intel.expected_move = expected_ratio(art, kind, z) * float(raw["atr15"])
    if intel.phase == "pre":
        price = _price(ctx, _done(ctx.struct("15m"), 900, now_i))
    else:  # the first-hour move is measured from the release: centre on the price then
        at = _done(_m5_set(ctx), 300, chosen) or _done(ctx.struct("15m"), 900, chosen)
        price = ctx.sp(at[-1].c) if at and at[-1].t + 900 >= chosen - STALE_S else None
    if price is not None:
        rng = (price - intel.expected_move, price + intel.expected_move)
        if intel.phase == "post" and now_i > chosen + 3600:
            intel.notes.append(f"Typical first-hour range (passed): {rng[0]:.2f} - {rng[1]:.2f}, around the price at the "
                               "release.")
        else:
            intel.expected_range = rng
    try:
        intel.probs, intel.tech_probs = _chances(art, row, kind)
        intel.coherence, intel.similar = neighbours(art, row, kind)
    except Exception as e:  # noqa: BLE001 - a model that cannot score must not take the app down
        print(f"[newsintel] model scoring failed: {type(e).__name__}: {e}", file=sys.stderr)
        intel.notes.append("The news models could not score this release.")
        intel.probs = intel.tech_probs = None
    intel.uncertain = (intel.probs is None or max(intel.probs.values()) < art.uncertain_max_p
                       or (intel.coherence is not None and intel.coherence > art.uncertain_bhatt))
    return intel


# ---------------------------------------------------------------- async entry point for the app

_inflight: dict[tuple[str, int], asyncio.Task] = {}


def _timed_out(now: float) -> Intel:
    return Intel(phase="none", notes=["News context took too long to build; skipped this time."])


async def build_intel_async(ctx: MarketContext, now: float, art, timeout: float = 8.0,
                            events: list[dict] | None = None) -> Intel:
    """build_intel in a worker thread under `timeout`, using only the remembered / on-disk surprise. After a
    release whose surprise is still unknown it starts one background FRED lookup per release (the 10-minute
    throttle in _default_surprise applies), so a later call picks the surprise up. Never raises, never waits
    for FRED."""
    try:
        intel = await asyncio.wait_for(asyncio.to_thread(build_intel, ctx, now, art, "cached", events), timeout)
    except asyncio.TimeoutError:
        return _timed_out(now)
    except Exception as e:  # noqa: BLE001 - never take the agent down
        print(f"[newsintel] build failed: {type(e).__name__}: {e}", file=sys.stderr)
        return Intel(phase="none", notes=["News context unavailable this time."])
    ev = intel.event
    if intel.phase == "post" and intel.surprise_z is None and ev and ev["kind"] in RELEASES:
        key = (ev["kind"], int(ev["t"]))
        task = _inflight.get(key)
        if (task is None or task.done()) and key not in _found                 and time.time() - _tried.get(key, 0.0) >= FRED_RETRY_S:
            _inflight[key] = asyncio.create_task(_background_surprise(*key))
    return intel


async def _background_surprise(kind: str, t: int) -> None:
    try:
        await asyncio.to_thread(_default_surprise, kind, t)
    except Exception as e:  # noqa: BLE001 - logged; the next window retries
        print(f"[newsintel] background surprise for {kind} failed: {type(e).__name__}: {str(e)[:200]}",
              file=sys.stderr)
