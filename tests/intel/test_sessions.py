from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from core.intel import sessions as S
from core.models import Candle

NYZ = ZoneInfo("America/New_York")
NPZ = Path(__file__).resolve().parents[2] / "data" / "news_intel" / "xau_1m.npz"


def ts(y, m, d, h, mi=0):
    return int(datetime(y, m, d, h, mi, tzinfo=NYZ).timestamp())


def bars(y, m, d0, days, f=lambda t: 100.0):
    out, t = [], ts(y, m, d0, 0)
    end = ts(y, m, d0 + days, 0)
    while t < end:
        p = f(t)
        out.append(Candle(t=t, o=p, h=p + 1, l=p - 1, c=p))
        t += 900
    return out


@pytest.mark.parametrize("y,m,d", [(2026, 3, 4), (2026, 11, 1)])    # DST changes Mar 8 and Nov 1
def test_windows_follow_ny_clock_across_dst(y, m, d):
    for day in range(d, d + 6):
        now = ts(y, m, day, 10) if not (m == 11 and day == 1) else ts(y, m, day, 10)
        s, e = S.asian_window(now)
        assert S.ny(s).hour == 20 and S.ny(e).hour == 0 and S.ny(e).date() == S.ny(now).date()
        assert S.current_sessions(ts(y, m, day, 9)).sessions == ["London", "New York", "London/New York overlap"]
        assert S.current_sessions(ts(y, m, day, 18)).low_liquidity
        assert not S.current_sessions(ts(y, m, day, 14)).low_liquidity


def test_asian_range_values_and_not_finished():
    c = bars(2026, 3, 4, 2, lambda t: 100 + (5 if S.ny(t).hour == 22 else 0))
    hi, lo = S.asian_range(c, ts(2026, 3, 5, 1))
    assert (hi, lo) == (106.0, 99.0)
    assert S.asian_range(c, ts(2026, 3, 4, 23)) is None            # still forming
    assert S.asian_range(c[:3], ts(2026, 3, 5, 1), min_bars=8) is None


def test_closed_candles_only():
    c = bars(2026, 3, 4, 1)
    now = ts(2026, 3, 4, 3, 35)
    r = S.session_range(c, "London", now)
    assert r.end > now and r.bars == 2          # 03:00 and 03:15 are closed; 03:30 still forming


def test_open_sweep_london_and_ny():
    def f(t):
        n = S.ny(t)
        if n.hour == 3 and n.minute == 15 and n.day == 5:
            return 110.0                   # spikes above Asian high, closes back below below
        return 100.0
    c = bars(2026, 3, 4, 3, f)
    # make the sweep bar close back inside the range
    for i, x in enumerate(c):
        if x.t == ts(2026, 3, 5, 3, 15):
            c[i] = Candle(t=x.t, o=100, h=110, l=99, c=100.5)
    sw = S.open_sweeps(c, ts(2026, 3, 5, 4))
    assert [(s.open_name, s.side) for s in sw] == [("London open", "buy")]
    assert "liquidity grab" in sw[0].text
    assert S.open_sweeps(c, ts(2026, 3, 5, 2)) == []


@pytest.mark.skipif(not NPZ.exists(), reason="backup candles missing")
def test_callers_unchanged_on_real_candles():
    """Old inline definitions vs the shared helper, on real 15m candles over many days incl. DST weeks."""
    from agents.ict import asian_range as ict_old
    z = np.load(NPZ)
    t, o, h, l, c = (z[k] for k in "tohlc")
    sec = 900
    # build 15m from the minute file
    keys = (t // sec) * sec
    uniq, first = np.unique(keys, return_index=True)
    last = np.append(first[1:], len(t))
    m15 = [Candle(t=int(u), o=float(o[a]), h=float(h[a:b].max()), l=float(l[a:b].min()), c=float(c[b - 1]))
           for u, a, b in zip(uniq, first, last)]
    checked = 0
    for y, m, d0 in ((2026, 3, 2), (2026, 10, 26), (2026, 6, 1), (2025, 11, 3), (2025, 3, 10)):
        base = ts(y, m, d0, 0)
        if base < m15[0].t or base > m15[-1].t:
            continue
        for k in range(0, 7 * 96, 7):
            now = base + k * 900
            w = [x for x in m15 if now - 3 * 86400 <= x.t <= now]
            if len(w) < 50:
                continue
            old = ict_old(w)
            new = S.asian_range(w, w[-1].t, "ny_evening", min_bars=8)
            assert old == new
            # old core/liquidity inline logic
            day0 = datetime.fromtimestamp(now, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            asia = [x for x in w if x.t >= day0 and x.t < day0 + 7 * 3600]
            exp = (max(x.h for x in asia), min(x.l for x in asia)) if asia and datetime.fromtimestamp(now, timezone.utc).hour >= 7 else None
            assert S.asian_range(w, now, "utc_0_7") == exp
            checked += 1
    assert checked > 50
