"""Measures how gold's 1-minute price reacted to one scheduled release at time T.

Price at x is the close of the last finished minute (see bars.price_at). Everything is in
USD. Only the pre-T candles are used for the volatility scale, so the label never depends
on candles from the event itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from core.indicators import atr
from core.newsintel.bars import price_at, resample, window
from core.newsintel.minutes import Minutes

MIN = 60
EXPECTED = 240       # 1-minute candles in [T - 60 min, T + 180 min)
MIN_COVERAGE = 0.9
SETTLE_FACTOR = 1.5
SIDE_ATR = 0.5       # |move| below this many ATRs is "side"


@dataclass
class Reaction:
    t: int
    p0: float | None
    r5: float | None
    r15: float | None
    r30: float | None
    r60: float | None
    r120: float | None
    max_up: float | None
    max_down: float | None
    vol_exp: float | None
    cont: int | None
    settle_min: int | None
    atr15: float | None
    move60: float | None
    move120: float | None
    label60: str | None
    label120: str | None
    incomplete: int


def _range(m: Minutes, a: int, b: int) -> float | None:
    """High minus low over candles with a <= t < b; None if there are none."""
    s = window(m, a, b)
    if s.stop <= s.start:
        return None
    return float(m.h[s].max() - m.l[s].min())


def _move(m: Minutes, a: int, b: int) -> float | None:
    pa, pb = price_at(m, a), price_at(m, b)
    return None if pa is None or pb is None else pb - pa


def _label(move: float | None, atr15: float | None) -> str | None:
    if move is None or not atr15:
        return None
    if abs(move) < SIDE_ATR * atr15:
        return "side"
    return "up" if move > 0 else "down"


def _pre_5min_median(m: Minutes, t: int) -> float | None:
    """Median of the rolling 5-minute ranges (one per minute) over [T - 60 min, T)."""
    rs = [_range(m, e - 5 * MIN, e) for e in range(t - 60 * MIN + 5 * MIN, t + 1, MIN)]
    rs = [r for r in rs if r is not None]
    return float(median(rs)) if rs else None


def _settle_min(m: Minutes, t: int) -> int | None:
    base = _pre_5min_median(m, t)
    if base is None:
        return None
    limit = SETTLE_FACTOR * base
    for k in range(1, 181):
        end = t + k * MIN
        s = window(m, end - 5 * MIN, end)
        if s.stop - s.start < 5:
            continue
        if float(m.h[s].max() - m.l[s].min()) <= limit:
            return k
    return None


def measure(m: Minutes, t: int, blackout_after_s: int) -> Reaction:
    """Reaction of gold to a release at t; blackout_after_s is how long trading is paused after it."""
    p0 = price_at(m, t)
    rets = {k: _move(m, t, t + k * MIN) for k in (5, 15, 30, 60, 120)}

    max_up = max_down = None
    if p0 is not None:
        s = window(m, t, t + 120 * MIN - MIN + 1)  # candles finished by T + 120 min
        if s.stop > s.start:
            max_up = float(m.h[s].max()) - p0
            max_down = p0 - float(m.l[s].min())

    pre, post = _range(m, t - 60 * MIN, t), _range(m, t, t + 30 * MIN)
    vol_exp = post / pre if pre and post is not None else None

    r5, r120 = rets[5], rets[120]
    cont = None
    if r5 and r120:  # None or 0 -> no direction
        cont = 1 if (r5 > 0) == (r120 > 0) else 0

    cs = resample(m, 15 * MIN, t, 60)
    a = atr(cs, 14)[-1] if cs else None
    tb = t + blackout_after_s
    move60, move120 = _move(m, tb, tb + 60 * MIN), _move(m, tb, tb + 120 * MIN)

    s = window(m, t - 60 * MIN, t + 180 * MIN)
    incomplete = int(s.stop - s.start < MIN_COVERAGE * EXPECTED)

    return Reaction(
        t=t, p0=p0, r5=rets[5], r15=rets[15], r30=rets[30], r60=rets[60], r120=r120,
        max_up=max_up, max_down=max_down, vol_exp=vol_exp, cont=cont,
        settle_min=_settle_min(m, t), atr15=a, move60=move60, move120=move120,
        label60=_label(move60, a), label120=_label(move120, a), incomplete=incomplete,
    )
