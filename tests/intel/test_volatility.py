import random

from core.intel import volatility as v
from core.models import Candle


def series(n, rng=1.0, base=100.0, seed=1):
    r = random.Random(seed)
    out, p = [], base
    for i in range(n):
        o = p
        c = o + r.uniform(-rng, rng) / 2
        out.append(Candle(t=i * 900, o=o, h=max(o, c) + rng / 2, l=min(o, c) - rng / 2, c=c))
        p = c
    return out


def test_fit_uses_only_before_until():
    cs = series(600) + series(200, rng=50, base=100, seed=2)
    for i, c in enumerate(cs):
        c.t = i * 900
    until = 600 * 900
    assert v.fit_vol(cs, until) == v.fit_vol(cs[:600])
    assert v.fit_vol(cs)["atr_ratio"]["abnormal"] > v.fit_vol(cs, until)["atr_ratio"]["abnormal"]


def test_regime_bands_and_text():
    cs = series(600)
    p = v.fit_vol(cs)
    assert v.regime(cs, p).regime in ("low", "normal", "high")
    wild = cs + series(8, rng=30, base=cs[-1].c, seed=3)
    r = v.regime(wild, p)
    assert r.regime == "abnormal" and r.trend == "expanding" and "avoid" in r.text.lower()
    assert r.max_stop == p["stop_k"] * r.atr


def test_unknown_without_params():
    r = v.regime(series(50), {})
    assert r.regime == "unknown" and r.text


def test_stop_check_never_widens():
    cs = series(600)
    p = v.fit_vol(cs)
    a = v.regime(cs, p).atr
    ok = v.stop_check({"entry_lo": 100, "entry_hi": 100, "stop": 100 - a}, cs, p)
    assert ok.ok and "within" in ok.text
    bad = v.stop_check({"entry_lo": 100, "entry_hi": 100, "stop": 100 - p["stop_k"] * a * 2}, cs, p)
    assert not bad.ok and "skip" in bad.text and bad.distance > bad.cap
