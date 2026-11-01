from core.intel import entry as e
from core.models import Candle

P = {"late_atr": 2.0}


def flat(n, base=100.0):
    return [Candle(t=i * 900, o=base, h=base + 0.5, l=base - 0.5, c=base) for i in range(n)]


def with_break(close_after, n_after=2):
    cs = flat(30)
    for k in range(n_after):
        px = 100.5 + 1 + k
        cs.append(Candle(t=len(cs) * 900, o=px - 1, h=px + 0.5, l=px - 1, c=px))
    cs[-1] = Candle(t=cs[-1].t, o=cs[-1].o, h=max(cs[-1].h, close_after), l=cs[-1].l, c=close_after)
    return cs


def plan(**k):
    d = {"side": "BUY", "entry_lo": 101.0, "entry_hi": 101.5, "stop": 99.0, "t1": 110.0}
    d.update(k)
    return d


class Pool:
    def __init__(self, price, status="untouched", sources=("previous day high",)):
        self.price, self.status, self.sources = price, status, list(sources)


def test_ok_when_near_zone_and_room():
    r = e.check_entry(plan(), with_break(102.0), {"above": [Pool(120)], "below": []}, P)
    assert r.ok and not r.late and r.retest_valid and r.room_ok and "pass" in r.text


def test_late_when_far_past_breakout():
    r = e.check_entry(plan(), with_break(106.0), {"above": [], "below": []}, P)
    assert r.late and not r.ok and "Late" in r.text


def test_retest_invalid_stop_or_target():
    r = e.check_entry(plan(stop=101.9), with_break(101.8), {}, P)
    assert not r.retest_valid and "stop" in r.text
    r = e.check_entry(plan(t1=102.0), with_break(102.0), {}, P)
    assert not r.retest_valid and "Target already" in r.text


def test_target_blocked_by_untouched_pool_only():
    r = e.check_entry(plan(), with_break(102.0), {"above": [Pool(105)]}, P)
    assert not r.room_ok and r.blocker["price"] == 105 and "blocked" in r.text
    r = e.check_entry(plan(), with_break(102.0), {"above": [Pool(105, "hunted")]}, P)
    assert r.room_ok
    r = e.check_entry(plan(), with_break(102.0), {"above": [{"price": 105, "status": "untouched", "sources": ["x"]}]}, P)
    assert not r.room_ok


def test_sell_side_uses_pools_below():
    cs = flat(30)
    cs.append(Candle(t=30 * 900, o=99.5, h=99.6, l=98, c=98.5))
    p = plan(side="SELL", entry_lo=98.5, entry_hi=99.0, stop=101.0, t1=90.0)
    r = e.check_entry(p, cs, {"above": [], "below": [Pool(95)]}, P)
    assert not r.room_ok and not r.ok


def test_fit_entry_no_lookahead():
    import random
    r = random.Random(5)
    cs, px = [], 100.0
    for i in range(1500):
        o = px
        px = o + r.uniform(-1, 1)
        cs.append(Candle(t=i * 900, o=o, h=max(o, px) + .3, l=min(o, px) - .3, c=px))
    a = e.fit_entry(cs, 1000 * 900)
    assert a == e.fit_entry(cs[:1000]) and a["late_atr"] > 0
