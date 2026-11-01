from core.models import Candle
from core.newsintel.m5 import m5_confirmations

T0 = 1_700_000_000


def mk(path):
    """path: list of (low, high, close); open = previous close."""
    out, prev = [], path[0][2]
    for i, (l, h, c) in enumerate(path):
        out.append(Candle(t=T0 + 300 * i, o=prev, h=h, l=l, c=c))
        prev = c
    return out


def base():
    """40 bars chopping 100-102, then a push to 110 and a pullback to 104: confirmed swing high 110."""
    p = [(99.5, 102, 100.5 if i % 2 else 101.5) for i in range(40)]
    p += [(101, 104, 103.5), (103, 107, 106.5), (106, 110, 109.5), (105, 109, 105.5), (103, 106, 104), (103, 105, 104)]
    return p


def test_break_up():
    c = mk(base() + [(104, 112, 111.5)])
    r = m5_confirmations(c)
    assert r["bos"] == "up" and r["retest"] is None and "break up" in r["text"]


def test_break_up_with_retest():
    c = mk(base() + [(104, 112, 111.5), (111, 113, 112.5), (109.9, 112, 111.2)])
    r = m5_confirmations(c)
    assert r["bos"] == "up" and r["retest"] == "up" and "retest" in r["text"]


def test_break_down():
    p = [(98, 100.5, 99.5 if i % 2 else 100) for i in range(40)]
    p += [(97, 99, 97.5), (93, 98, 93.5), (90, 94, 90.5), (91, 95, 94.5), (94, 96, 95.5), (94, 96, 95.5), (86, 95, 87)]
    r = m5_confirmations(mk(p))
    assert r["bos"] == "down" and r["retest"] is None


def test_no_break():
    r = m5_confirmations(mk([(99.5, 102, 100.5 if i % 2 else 101.5) for i in range(50)]))
    assert r["bos"] is None and r["retest"] is None


def test_old_break_ignored():
    c = mk(base() + [(104, 112, 111.5)] + [(111, 112.5, 111.8)] * 8)
    assert m5_confirmations(c)["bos"] is None


def test_too_few_candles():
    r = m5_confirmations(mk([(99, 101, 100)] * 10))
    assert r == {"bos": None, "retest": None, "text": "Not enough 5-minute candles"}
    assert m5_confirmations([])["bos"] is None
