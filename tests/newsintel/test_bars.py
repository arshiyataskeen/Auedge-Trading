from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from core.newsintel.bars import price_at, resample, session_day_candles, window
from core.newsintel.minutes import Minutes

NY = ZoneInfo("America/New_York")


def _mk(ts, closes=None):
    t = np.array(ts, dtype=np.int64)
    c = np.array(closes if closes is not None else range(len(ts)), dtype=np.float64)
    return Minutes(t, c.copy(), c + 0.5, c - 0.5, c)


def test_price_at_uses_finished_candle():
    m = _mk([0, 60, 120], [10, 11, 12])
    assert price_at(m, 120) == 11  # candle t=120 is still forming
    assert price_at(m, 180) == 12


def test_price_at_stale_is_none():
    m = _mk([0, 60], [10, 11])
    assert price_at(m, 120) == 11
    assert price_at(m, 60 + 60 + 31 * 60) is None
    assert price_at(m, 0) is None  # nothing finished yet


def test_window_half_open():
    m = _mk([0, 60, 120, 180])
    s = window(m, 60, 180)
    assert list(m.t[s]) == [60, 120]


def test_resample_15m_ohlc():
    m = _mk([i * 60 for i in range(30)])
    out = resample(m, 900, 29 * 60, 5)  # second bucket still forming
    assert len(out) == 1
    c = out[0]
    assert (c.t, c.o, c.c) == (0, 0, 14)
    assert c.h == 14.5 and c.l == -0.5
    out = resample(m, 900, 30 * 60, 5)
    assert [x.t for x in out] == [0, 900]
    assert (out[1].o, out[1].c) == (15, 29)
    assert len(resample(m, 900, 30 * 60, 1)) == 1


def test_session_day_split_at_18_ny():
    a = int(datetime(2024, 3, 6, 16, 59, tzinfo=NY).timestamp())
    b = int(datetime(2024, 3, 6, 18, 0, tzinfo=NY).timestamp())
    m = _mk([a, b], [1, 2])
    end = int(datetime(2024, 3, 8, 0, 0, tzinfo=NY).timestamp())
    out = session_day_candles(m, end, 5)
    assert [x.c for x in out] == [1, 2]
    assert out[0].t == int(datetime(2024, 3, 6, tzinfo=NY).timestamp())
    assert out[1].t == int(datetime(2024, 3, 7, tzinfo=NY).timestamp())


def test_session_day_excludes_unfinished():
    b = int(datetime(2024, 3, 6, 18, 0, tzinfo=NY).timestamp())
    m = _mk([b], [2])
    end = int(datetime(2024, 3, 7, 16, 0, tzinfo=NY).timestamp())  # session ends 17:00
    assert session_day_candles(m, end, 5) == []
    end = int(datetime(2024, 3, 7, 17, 0, tzinfo=NY).timestamp())
    assert len(session_day_candles(m, end, 5)) == 1


def test_session_day_excludes_closed_hour_and_future():
    d = lambda h, mi: int(datetime(2024, 3, 7, h, mi, tzinfo=NY).timestamp())
    m = _mk([d(16, 58), d(16, 59), d(17, 0), d(17, 30)], [1, 2, 99, 99])
    out = session_day_candles(m, d(17, 0), 1)
    assert len(out) == 1 and out[0].h == 2.5 and out[0].c == 2
    # end inside the closed hour: minutes at or after end never leak in
    out = session_day_candles(m, d(17, 20), 1)
    assert out[0].h == 2.5  # 17:00 minute is in the closed hour, excluded too


def test_resample_n_zero_returns_empty():
    m = _mk([i * 60 for i in range(30)])
    assert resample(m, 900, 30 * 60, 0) == []
    assert resample(m, 900, 30 * 60, -1) == []


def test_price_at_stale_boundary():
    m = _mk([0], [10])
    assert price_at(m, 60 + 1800) == 10
    assert price_at(m, 60 + 1801) is None


def test_resample_across_weekend_gap_returns_n():
    ts = list(range(0, 30 * 60, 60)) + list(range(172800, 172800 + 30 * 60, 60))
    m = _mk(ts)
    out = resample(m, 900, 172800 + 30 * 60, 4)
    assert [c.t for c in out] == [0, 900, 172800, 172800 + 900]
