import numpy as np

from core.newsintel.minutes import Minutes
from core.newsintel.reactions import measure

T = 1_700_000_100 // 900 * 900  # on a 15-minute boundary


def _minutes(post, lo=-360, hi=180):
    """1-minute candles for minute offsets lo..hi-1 around T. Before T the close alternates
    2000 +/- 0.5 (so ATR > 0) and the last pre-T close is exactly 2000 (P0 = 2000).
    `post(k)` gives the close of the candle starting T + k min (k >= 0)."""
    ks = np.arange(lo, hi)
    c = np.array([post(int(k)) if k >= 0 else (2000.0 if k == -1 else 2000.0 + (0.5 if k % 2 == 0 else -0.5))
                  for k in ks])
    return Minutes(T + ks * 60, c.copy(), c + 0.25, c - 0.25, c)


def test_returns_at_horizons():
    m = _minutes(lambda k: 2000.0 + k + 1)  # +1 USD per minute
    r = measure(m, T, 1800)
    assert r.p0 == 2000.0
    assert (r.r5, r.r15, r.r30, r.r60, r.r120) == (5, 15, 30, 60, 120)
    assert r.incomplete == 0


def test_excursions_and_vol_exp():
    # up to +10 over the first 10 minutes, back to -4 by minute 20, then flat
    def post(k):
        if k < 10:
            return 2000.0 + k + 1
        return max(2010.0 - (k - 9) * 1.4, 1996.0)
    r = measure(_minutes(post), T, 1800)
    assert abs(r.max_up - 10.25) < 1e-9
    assert abs(r.max_down - 4.25) < 1e-9
    # pre range 1.5 (1999.25..2000.75 with 2000 close), event range 14.5
    assert r.vol_exp is not None and r.vol_exp > 5


def test_vol_exp_none_without_pre_data():
    m = _minutes(lambda k: 2000.0 + k, lo=0)
    assert measure(m, T, 1800).vol_exp is None


def test_continuation_vs_reversal():
    up_then_down = measure(_minutes(lambda k: 2000.0 + k + 1 if k < 5 else 1980.0), T, 1800)
    assert up_then_down.r5 == 5 and up_then_down.r120 == -20 and up_then_down.cont == 0
    steady = measure(_minutes(lambda k: 2000.0 + k + 1), T, 1800)
    assert steady.cont == 1
    flat = measure(_minutes(lambda k: 2000.0), T, 1800)
    assert flat.cont is None


def test_labels_use_blackout_end():
    atr = measure(_minutes(lambda k: 2000.0), T, 1800).atr15
    assert atr and atr > 0
    # move only inside the 30 min blackout -> nothing left to trade
    inside = measure(_minutes(lambda k: 2050.0 if k >= 5 else 2000.0), T, 1800)
    assert inside.label60 == "side" and inside.label120 == "side"
    # a 3 ATR jump after Tb
    jump = lambda k: 2000.0 + (3 * atr if k >= 45 else 0.0)
    r = measure(_minutes(jump), T, 1800)
    assert r.label60 == "up" and abs(r.move60 - 3 * atr) < 1e-9
    down = measure(_minutes(lambda k: 2000.0 - (3 * atr if k >= 45 else 0.0)), T, 1800)
    assert down.label60 == "down"
    # FOMC: Tb = T + 60 min, so the same jump at minute 45 falls inside the blackout
    fomc = measure(_minutes(jump), T, 3600)
    assert fomc.label60 == "side"


def test_no_volatility_scale_gives_no_label():
    m = _minutes(lambda k: 2000.0 + k, lo=-3)  # too little history for ATR
    r = measure(m, T, 1800)
    assert r.atr15 is None and r.label60 is None and r.label120 is None


def test_settle_minutes():
    # 10 wild minutes, then calm: first 5-candle window that is all calm ends at minute 15
    r = measure(_minutes(lambda k: 2000.0 + (10 if k % 2 == 0 else -10) if k < 10 else 2000.0), T, 1800)
    assert r.settle_min == 15
    never = measure(_minutes(lambda k: 2000.0 + (10 if k % 2 == 0 else -10)), T, 1800)
    assert never.settle_min is None


def test_reaction_when_market_closed():
    e = np.array([], dtype=np.int64)
    f = np.array([], dtype=np.float64)
    r = measure(Minutes(e, f, f, f, f), T, 1800)
    assert r.incomplete == 1 and r.p0 is None
    assert r.r5 is None and r.max_up is None and r.label60 is None and r.settle_min is None


def test_incomplete_when_sparse():
    assert measure(_minutes(lambda k: 2000.0, hi=100), T, 1800).incomplete == 1


def test_settle_window_never_reaches_before_t():
    # calm from T on: the first window wholly at/after T ends at T + 5 min
    assert measure(_minutes(lambda k: 2000.0), T, 1800).settle_min == 5
