from core.intel.structure_q import analyze
from core.models import Candle


def _c(i, o, h, l, c):
    return Candle(t=1_700_000_000 + i * 900, o=o, h=h, l=l, c=c, v=1)


def _wave(tail):
    """Range 100-110 (several swings), then `tail` = list of (o,h,l,c)."""
    cs, i, px = [], 0, 105.0
    for _ in range(6):
        for tgt in (110.0, 100.0):
            for _ in range(5):
                n = px + (tgt - px) / 5 * 1
                cs.append(_c(i, px, max(px, n) + 0.5, min(px, n) - 0.5, n)); px = n; i += 1
    cs.append(_c(i, px, 110.5, 109.5, 110.0)); i += 1   # confirmed high at ~110.5
    for t in tail:
        cs.append(_c(i, *t)); i += 1
    return cs


def test_buy_sweep_then_strong_close_break_ok():
    # sweep below 100 (wick to 98, close 101), then climb and close above 110.5 with a big body
    tail = [(103, 103.5, 98, 101), (101, 105, 100.5, 104.5), (104.5, 109, 104, 108.5), (108.5, 116, 108, 115.5)]
    r = analyze(_wave(tail), "BUY")
    assert r.swept and r.bos and r.ok and not r.failed and r.body_strength > 0.8 and "hunted" in r.text


def test_failed_breakout_not_ok():
    tail = [(103, 103.5, 98, 101), (101, 105, 100.5, 104.5), (104.5, 109, 104, 108.5), (108.5, 116, 108, 115.5),
            (115.5, 115.6, 105, 106)]
    r = analyze(_wave(tail), "BUY")
    assert r.bos and r.failed and not r.ok and "failed" in r.text


def test_no_sweep_no_ok_and_short_data():
    assert not analyze(_wave([(105, 106, 104, 105)]), "BUY").ok
    r = analyze(_wave([])[:10], "BUY")
    assert not r.ok and r.text
