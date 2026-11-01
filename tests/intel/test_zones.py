from core.intel.zones import find_zones
from core.models import Candle

T0 = 1_800_000_000


def mk(i, o, h, l, c):
    return Candle(t=T0 + i * 900, o=o, h=h, l=l, c=c)


def base(n=30, p=100.0):
    return [mk(i, p, p + 1, p - 1, p + (0.2 if i % 2 else -0.2)) for i in range(n)]


def kinds(zs):
    return sorted((z.kind, z.side) for z in zs.zones)


def test_unfilled_bull_fvg_and_filled_one_dropped():
    c = base()
    c += [mk(30, 100, 100.5, 99.5, 100.2), mk(31, 100.2, 106, 100.1, 105.5), mk(32, 105.5, 107, 104, 106)]
    z = find_zones(c)
    fvg = [x for x in z.zones if x.kind == "FVG"]
    assert len(fvg) == 1 and fvg[0].side == "bull" and (fvg[0].low, fvg[0].high) == (100.5, 104)
    c.append(mk(33, 106, 106, 102, 103))                 # trades into the gap -> mitigated
    assert not [x for x in find_zones(c).zones if x.kind == "FVG"]


def test_bull_order_block_then_breaker():
    c = base()
    c += [mk(30, 100.4, 100.5, 98.5, 99), mk(31, 99, 106, 98.9, 105.8), mk(32, 105.8, 106.5, 105, 106)]
    z = find_zones(c)
    ob = [x for x in z.zones if x.kind == "order block"]
    assert ob and ob[0].side == "bull" and (ob[0].low, ob[0].high) == (98.5, 100.5)
    c += [mk(33, 106, 106, 97, 97.5), mk(34, 97.5, 98, 96, 97)]      # closes below the block -> breaker (bear)
    z2 = find_zones(c, price=97)
    br = [x for x in z2.zones if x.kind == "breaker"]
    assert br and br[0].side == "bear" and not [x for x in z2.zones if x.kind == "order block" and x.side == "bull"]


def test_rejection_block_lower_wick():
    c = base()
    c += [mk(30, 100, 100.4, 95, 100.2), mk(31, 100.2, 101, 100, 100.6)]
    z = find_zones(c)
    rj = [x for x in z.zones if x.kind == "rejection"]
    assert rj and rj[0].side == "bull" and rj[0].low == 95 and "buyers rejected" in rj[0].text


def test_closed_candles_only_and_near_text():
    c = base() + [mk(30, 100, 100.4, 95, 100.2)]
    now = T0 + 30 * 900 + 100                           # last candle still forming
    assert not [x for x in find_zones(c, now_t=now).zones if x.kind == "rejection"]
    z = find_zones(c)
    assert z.near and z.text.startswith("Nearby zones")
    assert find_zones(base(5)).text.startswith("Not enough")
