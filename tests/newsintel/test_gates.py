import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from core import news
from core.models import Candle
from core.newsintel import gates, store
from agents.psychology import assess

NY = news.NY


def _t(day, hh, mm):
    return news._at_ny(day, hh, mm)


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "ni.db"
    with store.connect(p) as con:
        con.execute("INSERT INTO events (kind, name, t) VALUES ('PPI', 'PPI', ?)", (_t("2024-03-14", 8, 30),))
    monkeypatch.setattr(gates, "DB", p)
    gates._cache.clear()
    yield p
    gates._cache.clear()


def art(p99=2.5):
    return SimpleNamespace(m5_range_p99=p99)


def m5(last_range, n=30):
    cs = [Candle(t=1_700_000_000 + 300 * i, o=100, h=100.5, l=99.5, c=100) for i in range(n)]
    cs[-1] = Candle(t=cs[-1].t, o=100, h=100 + last_range / 2, l=100 - last_range / 2, c=100)
    return cs


def test_historical_ppi_from_db_blocks_but_core_misses(db):
    ts = _t("2024-03-14", 8, 20)
    assert news.blackout(ts) is None
    ev = gates.blackout(ts)
    assert ev and ev["kind"] == "PPI"
    assert gates.avoid(ts, None, None, None, None, None)[0] == "calendar"
    assert gates.blackout(_t("2024-03-14", 9, 10)) is None


def test_fomc_60_minutes_after_blocks(db):
    fomc = next(e for e in news.events() if e["kind"] == "FOMC")
    assert gates.blackout(fomc["t"] + 3500)["kind"] == "FOMC"
    assert gates.blackout(fomc["t"] + 3700) is None or gates.blackout(fomc["t"] + 3700)["kind"] != "FOMC"


def test_dedup_per_ten_minute_slot(db):
    ev = news.events()[0]
    with store.connect(db) as con:
        con.execute("INSERT INTO events (kind, name, t) VALUES (?, 'dup', ?)", (ev["kind"], ev["t"] + 60))
    gates._cache.clear()
    ts = [e["t"] // 600 for e in gates.calendar_events()]
    assert len(ts) == len(set(ts))
    assert ts == sorted(ts)


QUIET = _t("2024-03-13", 11, 0)


def test_volatility_threshold(db):
    a = art(2.5)
    hi = gates.avoid(QUIET, m5(8.0), None, None, None, a)   # ratio well above 2.5
    assert hi and hi[0] == "volatility" and "10" in hi[1]
    assert gates.avoid(QUIET, m5(1.0), None, None, None, a) is None


def test_spread_gate(db):
    a = art()
    r = gates.avoid(QUIET, None, 0.31, 0.10, None, a)
    assert r and r[0] == "spread"
    assert gates.avoid(QUIET, None, 0.29, 0.10, None, a) is None
    assert gates.avoid(QUIET, None, None, 0.10, None, a) is None
    assert gates.avoid(QUIET, None, 0.31, None, None, a) is None


def test_uncertain_only_inside_window(db):
    a = art()
    t = QUIET
    post = {"phase": "post", "uncertain": True, "event": {"kind": "CPI", "t": t - 3600}}
    pre_near = {"phase": "pre", "uncertain": True, "event": {"kind": "CPI", "t": t + 3600}}
    pre_far = {"phase": "pre", "uncertain": True, "event": {"kind": "CPI", "t": t + 5 * 3600}}
    none = {"phase": "none", "uncertain": True, "event": None}
    sure = {"phase": "post", "uncertain": False, "event": {"kind": "CPI", "t": t - 3600}}
    assert gates.avoid(t, None, None, None, post, a)[0] == "uncertain"
    assert gates.avoid(t, None, None, None, pre_near, a)[0] == "uncertain"
    for i in (pre_far, none, sure):
        assert gates.avoid(t, None, None, None, i, a) is None


def test_no_artifacts_only_calendar(db):
    ts = _t("2024-03-14", 8, 20)
    assert gates.avoid(ts, m5(50.0), 9.0, 1.0, {"phase": "post", "uncertain": True, "event": {"t": ts}}, None)[0] == "calendar"
    assert gates.avoid(QUIET, m5(50.0), 9.0, 1.0, {"phase": "post", "uncertain": True, "event": {"t": QUIET}}, None) is None


def test_order_calendar_first(db):
    ts = _t("2024-03-14", 8, 20)
    assert gates.avoid(ts, m5(8.0), 0.9, 0.1, None, art())[0] == "calendar"


STATS = dict(trades_today=0, wins_today=0, losses_today=0, usd_today=0.0, last_loss_ts=0, open=False,
             losing_streak=0, r_today=0.0)


def test_assess_unchanged_without_new_args():
    now = datetime(2024, 3, 13, 16, 0, tzinfo=timezone.utc)
    a = assess(dict(STATS), now, [], [])
    assert a["blocks"] == [] and a["warns"] == []
    assert assess(dict(STATS), now, [], [], m5=None, spread=None, intel=None) == a


def test_assess_blocks_with_gate(db):
    now = datetime(2024, 3, 13, 16, 0, tzinfo=timezone.utc)
    a = assess(dict(STATS), now, [], [], m5=m5(8.0), art=art(2.5))
    assert any("5-minute" in b for b in a["blocks"])
