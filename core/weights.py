"""Performance-based agent weights: trust agents that have actually been right, carefully.

Rules (same live and in the backtest):
- Score: each BUY/SELL call is checked 4 hours later (hit = price moved $3+ its way, miss = $3+ against; the same
  rule as the track record). Only calls already scored before the update time are used: no look-ahead.
- Window: the last 60 days. Update: once a week (trading week starts Sunday 18:00 New York).
- Calls repeat every 15 minutes and overlap, so only one call per agent per 4 hours is counted.
- At least 100 scored calls, otherwise the agent keeps its default weight.
- Shrunk toward 50%: the hit rate counts as if there were 100 extra calls at exactly 50%, so a short lucky run
  barely moves the weight.
- Multiplier = 1 + 10 x (shrunk hit rate - 50%), limited to 0.5x .. 1.5x of the agent's default weight.
  Example: 55% over 400 calls -> shrunk 54% -> x1.40. 47% over 400 calls -> shrunk 47.6% -> x0.76.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
WINDOW_S = 60 * 86400
MIN_CALLS = 100
PRIOR_CALLS = 100
SLOPE = 10.0
LO, HI = 0.5, 1.5
SPACING_S = 4 * 3600         # one call per agent per 4 hours counts (the scoring horizon)


def week_start(ts: float) -> int:
    """Start of the trading week containing ts: the latest Sunday 18:00 New York at or before ts."""
    ny = datetime.fromtimestamp(ts, NY)
    sunday = (ny - timedelta(days=(ny.weekday() + 1) % 7)).replace(hour=18, minute=0, second=0, microsecond=0)
    if sunday > ny:
        sunday -= timedelta(days=7)
    return int(sunday.timestamp())


def multipliers(scored: list[tuple[str, float, str]], at: float) -> dict[str, dict]:
    """scored = (agent, call_time, 'hit'|'miss'|'flat') with the outcome known by `at` (call_time + 4h <= at).
    Returns {agent: {mult, n, hit_rate, shrunk}} for agents that have any scored calls in the window."""
    out: dict[str, dict] = {}
    last: dict[str, float] = {}
    for agent, t, outcome in sorted(scored, key=lambda x: x[1]):
        # Calls repeat every 15 minutes and overlap; count at most one per agent per 4 hours (independent outcomes).
        if at - WINDOW_S > t or t - last.get(agent, -1e12) < SPACING_S:
            continue
        last[agent] = t
        if outcome in ("hit", "miss"):
            a = out.setdefault(agent, {"hits": 0, "n": 0})
            a["n"] += 1
            a["hits"] += outcome == "hit"
    for agent, a in out.items():
        raw = a["hits"] / a["n"]
        shrunk = (a["hits"] + 0.5 * PRIOR_CALLS) / (a["n"] + PRIOR_CALLS)
        mult = min(HI, max(LO, 1 + SLOPE * (shrunk - 0.5))) if a["n"] >= MIN_CALLS else 1.0
        a.update(hit_rate=round(100 * raw, 1), shrunk=round(100 * shrunk, 1), mult=round(mult, 2))
    return out


def apply(base: dict[str, float], mult: dict[str, dict]) -> dict[str, float]:
    """Base weights (0 for non-voting agents) times this week's multipliers."""
    return {k: (w * mult[k]["mult"] if k in mult else w) for k, w in base.items()}
