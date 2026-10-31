from datetime import datetime

import numpy as np

from agents.chief import TFS
from core.indicators import atr
from core.newsintel.bars import NY, resample, session_day_candles
from core.newsintel.features import features
from core.newsintel.minutes import Minutes
from core.structure import tf_bias

T = int(datetime(2024, 3, 12, 8, 30, tzinfo=NY).timestamp())


def _walk(seed, t_end, days=130, drift=0.02):
    """Continuous 1-minute random walk (with drift) ending just before t_end."""
    n = days * 1440
    t = t_end - 60 * np.arange(n, 0, -1)
    rng = np.random.default_rng(seed)
    c = 2000.0 + np.cumsum(rng.normal(drift, 0.4, n))
    o = np.concatenate([[c[0]], c[:-1]])
    return Minutes(t.astype(np.int64), o, np.maximum(o, c) + 0.2, np.minimum(o, c) - 0.2, c)


def _hand_trend(m, t):
    sources = {"1d": session_day_candles(m, t, 120), "4h": resample(m, 14400, t, 120),
               "1h": resample(m, 3600, t, 120), "15m": resample(m, 900, t, 120)}
    total = 0.0
    for key, _name, mult, w in TFS:
        cs = sources[key]
        if len(cs) >= 60:
            total += w * max(-1.0, min(1.0, tf_bias(cs, mult)["score"] / 2.5))
    return total


def test_trend_score_matches_chief_formula():
    m = _walk(1, T + 3600)
    f = features(m, T, T - 7200)
    assert f.trend_score is not None and f.trend_score > 0  # uptrend
    assert abs(f.trend_score - _hand_trend(m, T)) < 1e-12
    assert f.hours_since_prev == 2.0
    assert abs(f.atr15 - atr(resample(m, 900, T, 60), 14)[-1]) < 1e-12
    assert abs(f.atr1h - atr(resample(m, 3600, T, 60), 14)[-1]) < 1e-12
    lo = int(np.searchsorted(m.t, T - 3600))
    hi = int(np.searchsorted(m.t, T))
    assert abs(f.pre_range - (m.h[lo:hi].max() - m.l[lo:hi].min())) < 1e-12


def test_no_lookahead_features():
    m = _walk(2, T + 7200)
    base = features(m, T, None)
    c = m.c.copy()
    o, h, l = m.o.copy(), m.h.copy(), m.l.copy()
    late = m.t + 60 > T  # not finished by T
    assert late.sum() > 100
    rng = np.random.default_rng(99)
    n = int(late.sum())
    r = 2000.0 + rng.normal(0, 500.0, n)
    o[late], c[late], h[late], l[late] = r, r + 1, r + 300, r - 300
    again = features(Minutes(m.t, o, h, l, c), T, None)
    assert again == base
    assert base.hours_since_prev is None


def test_overlap_flag():
    def f(h, mi):
        t = int(datetime(2024, 3, 12, h, mi, tzinfo=NY).timestamp())
        return features(_walk(3, t + 600, days=1), t, None).overlap
    assert f(8, 30) == 1
    assert f(14, 0) == 0
    assert f(7, 59) == 0
    assert f(11, 59) == 1
    assert f(12, 0) == 0
