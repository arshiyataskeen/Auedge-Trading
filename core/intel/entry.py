"""Entry quality checks for a Chief trade plan: late entry, retest still valid, room to the target.

Inputs: plan dict (side BUY/SELL, entry_lo, entry_hi, stop, t1), closed 15m candles, and the liquidity map
from core.liquidity.build_stop_map ({"above": [Pool], "below": [Pool]}). Reports only: never changes risk or stops.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.indicators import atr

BREAK_N = 20        # a breakout closes beyond the prior 20-bar extreme
RECENT = 12         # only breakouts in the last 12 bars matter (3 h)
AFTER = 4           # fit_entry: extension measured over the 4 bars after a breakout


@dataclass
class EntryResult:
    late: bool
    retest_valid: bool
    room_ok: bool
    ok: bool
    blocker: dict | None = None     # {"price", "sources"} of the pool in the way
    reasons: list[str] = field(default_factory=list)
    text: str = ""


def _get(p, k):
    return p[k] if isinstance(p, dict) else getattr(p, k)


def fit_entry(candles, until: int | None = None) -> dict:
    """late_atr = 75th percentile of how far (in ATR) price extends beyond a 20-bar breakout within 4 bars."""
    cs = [c for c in candles if until is None or c.t < until]
    a = atr(cs)
    ext = []
    for i in range(BREAK_N, len(cs) - AFTER):
        if not a[i]:
            continue
        hi, lo = max(c.h for c in cs[i - BREAK_N:i]), min(c.l for c in cs[i - BREAK_N:i])
        if cs[i].c > hi:
            ext.append((max(c.c for c in cs[i:i + AFTER + 1]) - hi) / a[i])
        elif cs[i].c < lo:
            ext.append((lo - min(c.c for c in cs[i:i + AFTER + 1])) / a[i])
    if len(ext) < 50:
        raise ValueError("not enough breakouts to fit entry parameters")
    return {"late_atr": float(np.percentile(ext, 75)), "n": len(ext)}


def _breakout_level(cs, buy: bool):
    """Level of the most recent breakout within RECENT bars, or None."""
    for i in range(len(cs) - 1, max(len(cs) - 1 - RECENT, BREAK_N - 1), -1):
        w = cs[i - BREAK_N:i]
        if buy and cs[i].c > max(c.h for c in w):
            return max(c.h for c in w)
        if not buy and cs[i].c < min(c.l for c in w):
            return min(c.l for c in w)
    return None


def check_entry(plan: dict, candles, pools: dict, params: dict | None = None) -> EntryResult:
    from core.intel.volatility import load_params
    params = params if params is not None else load_params().get("entry", {})
    late_x = params.get("late_atr")
    buy = str(plan["side"]).upper() == "BUY"
    a = atr(candles) if candles else []
    last = candles[-1] if candles else None
    if not a or a[-1] is None or last is None:
        return EntryResult(False, True, True, True, text="Entry checks skipped (not enough candles).")
    av, reasons = a[-1], []
    lo, hi, stop, t1 = plan["entry_lo"], plan["entry_hi"], plan["stop"], plan["t1"]

    # 1) late: price already ran too far from the breakout level
    late = False
    lvl = _breakout_level(candles, buy)
    if lvl is not None and late_x is not None:
        ext = ((last.c - lvl) if buy else (lvl - last.c)) / av
        if ext > late_x:
            late = True
            reasons.append(f"Late entry: price is {ext:.1f} ATR past the breakout at {lvl:.1f} "
                           f"(normal is up to {late_x:.1f}). Chasing it is poor value.")

    # 2) retest still valid: stop and target untouched, price back near the zone
    broke = last.c <= stop if buy else last.c >= stop
    done = last.h >= t1 if buy else last.l <= t1
    away = (last.c - hi) if buy else (lo - last.c)           # how far price is beyond the zone, in trade direction
    gone = late_x is not None and away > late_x * av
    retest = not (broke or done or gone)
    if broke:
        reasons.append("Retest failed: price already closed beyond the stop.")
    elif done:
        reasons.append("Target already reached before entry: the move is over.")
    elif gone:
        reasons.append("Price ran away from the entry zone without retesting it: the setup has left.")

    # 3) room: nearest untouched opposing pool must not sit before the target
    room, blocker = True, None
    side_pools = pools.get("above" if buy else "below", []) if pools else []
    for p in sorted(side_pools, key=lambda p: _get(p, "price") * (1 if buy else -1)):
        px = _get(p, "price")
        ahead = px > hi if buy else px < lo
        before_t1 = px < t1 if buy else px > t1
        if ahead and before_t1 and _get(p, "status") == "untouched":
            room, blocker = False, {"price": px, "sources": list(_get(p, "sources"))}
            reasons.append(f"Target blocked: {', '.join(blocker['sources'])} at {px:.1f} sits between entry "
                           f"and the {t1:.1f} target, so price may stall or reverse there.")
            break

    ok = not late and retest and room
    text = ("Entry checks pass: not late, retest valid, clear room to the target." if ok
            else " ".join(reasons))
    return EntryResult(late, retest, room, ok, blocker, reasons, text)
