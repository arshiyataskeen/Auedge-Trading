from datetime import datetime
from zoneinfo import ZoneInfo

from core.intel.align import align_state, opposes
from core.intel.levels import compute_levels
from core.models import Candle

NYZ = ZoneInfo("America/New_York")


def mk(y, m, d, h, mi, o):
    t = int(datetime(y, m, d, h, mi, tzinfo=NYZ).timestamp())
    return Candle(t=t, o=o, h=o + 1, l=o - 1, c=o + 0.5)


def series(y, m, d0, days):
    out, p = [], 100.0
    for d in range(d0, d0 + days):
        for h in range(24):
            for mi in (0, 15, 30, 45):
                out.append(mk(y, m, d, h, mi, p))
                p += 0.1
    return out


def test_daily_open_rolls_at_17_ny_around_dst():
    for y, m, d0 in ((2026, 3, 6), (2026, 11, 1), (2026, 7, 6)):
        c = series(y, m, d0, 3)
        c = [x for x in c if x.t <= mk(y, m, d0 + 2, 10, 0, 0).t]
        L = compute_levels(c, [])
        first = next(x for x in c if x.t == mk(y, m, d0 + 1, 17, 0, 0).t)
        assert L.daily_open == first.o


def test_weekly_open_after_sunday_17():
    c = [x for x in series(2026, 11, 2, 8) if x.t <= mk(2026, 11, 10, 9, 0, 0).t]
    L = compute_levels(c, [])
    wk = next(x for x in c if x.t == mk(2026, 11, 8, 17, 0, 0).t)
    assert L.weekly_open == wk.o


def test_sessions_and_prev():
    c = [x for x in series(2026, 6, 2, 3) if x.t <= mk(2026, 6, 4, 9, 0, 0).t]
    L = compute_levels(c, [])
    assert L.london and L.prev_london and L.newyork and L.prev_newyork
    assert L.london[0] > L.prev_london[0]


def test_align_logic():
    assert align_state(1, 1) == "aligned_up" and align_state(-1, -1) == "aligned_down"
    assert align_state(1, -1) == "mixed" and align_state(0, 1) == "mixed"
    assert opposes("aligned_down", "BUY") and opposes("aligned_up", "SELL")
    assert not opposes("mixed", "BUY") and not opposes("aligned_up", "BUY")
