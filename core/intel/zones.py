"""Confluence zones from closed candles: unmitigated FVGs, order blocks, breakers and rejection blocks.

Bull zones sit below price (support), bear zones above (resistance). Confluence only: nothing here blocks a trade.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.indicators import atr as _atr

DISP_BODY = 0.6        # displacement candle: body >= 60% of its range ...
DISP_ATR = 1.2         # ... and range >= 1.2 ATR
WICK_FRAC = 0.6        # rejection candle: one wick >= 60% of range
REJ_ATR = 0.8          # ... and range >= 0.8 ATR


@dataclass
class Zone:
    kind: str            # "FVG" | "order block" | "breaker" | "rejection"
    side: str            # "bull" (support) | "bear" (resistance)
    low: float
    high: float
    t: int
    text: str


@dataclass
class ZoneSet:
    zones: list[Zone] = field(default_factory=list)
    near: list[Zone] = field(default_factory=list)     # within near_atr x ATR of price
    text: str = ""


def _fmt(z_low, z_high):
    return f"{z_low:.2f}-{z_high:.2f}"


def find_zones(candles, now_t=None, tf: int = 900, price: float | None = None,
               near_atr: float = 2.0, lookback: int = 80) -> ZoneSet:
    cs = [c for c in candles if now_t is None or c.t + tf <= now_t]
    if len(cs) < 20:
        return ZoneSet(text="Not enough candles to map zones.")
    a = _atr(cs)
    n = len(cs)
    start = max(2, n - lookback)
    zones: list[Zone] = []
    for i in range(start, n):
        c = cs[i]
        av = a[i] or a[-1] or 0
        if not av:
            continue
        # FVG: candles i-2 and i leave a gap that candle i-1 spans; kept only if no later candle has entered it
        p = cs[i - 2]
        later = cs[i + 1:]
        if c.l > p.h and (c.l - p.h) >= 0.1 * av:
            if not any(x.l < c.l for x in later):
                zones.append(Zone("FVG", "bull", p.h, c.l, cs[i - 1].t,
                                  f"Unfilled bullish gap {_fmt(p.h, c.l)}: price may find support there."))
        if c.h < p.l and (p.l - c.h) >= 0.1 * av:
            if not any(x.h > c.h for x in later):
                zones.append(Zone("FVG", "bear", c.h, p.l, cs[i - 1].t,
                                  f"Unfilled bearish gap {_fmt(c.h, p.l)}: price may meet resistance there."))
        rng = c.h - c.l
        if rng <= 0:
            continue
        body = abs(c.c - c.o)
        # displacement -> order block (last opposing candle before it), then breaker if the block was broken
        if body >= DISP_BODY * rng and rng >= DISP_ATR * av and i >= 1:
            up = c.c > c.o
            j = next((k for k in range(i - 1, max(i - 6, -1), -1) if (cs[k].c < cs[k].o) == up and cs[k].c != cs[k].o), None)
            if j is not None:
                ob = cs[j]
                lo, hi = ob.l, ob.h
                after = cs[i + 1:]
                if up:
                    broken = next((x for x in after if x.c < lo), None)
                    touched = any(x.l <= hi for x in after)
                    if broken is not None:
                        zones.append(Zone("breaker", "bear", lo, hi, ob.t,
                                          f"Broken bullish order block {_fmt(lo, hi)} now acts as a breaker (resistance)."))
                    elif not touched:
                        zones.append(Zone("order block", "bull", lo, hi, ob.t,
                                          f"Untested bullish order block {_fmt(lo, hi)} (last down candle before a strong rally)."))
                else:
                    broken = next((x for x in after if x.c > hi), None)
                    touched = any(x.h >= lo for x in after)
                    if broken is not None:
                        zones.append(Zone("breaker", "bull", lo, hi, ob.t,
                                          f"Broken bearish order block {_fmt(lo, hi)} now acts as a breaker (support)."))
                    elif not touched:
                        zones.append(Zone("order block", "bear", lo, hi, ob.t,
                                          f"Untested bearish order block {_fmt(lo, hi)} (last up candle before a strong drop)."))
        # rejection block: long-wick candle, zone = the wick
        if rng >= REJ_ATR * av:
            top, bot = max(c.o, c.c), min(c.o, c.c)
            later = cs[i + 1:]
            if c.h - top >= WICK_FRAC * rng and not any(x.h >= c.h for x in later):
                zones.append(Zone("rejection", "bear", top, c.h, c.t,
                                  f"Long upper wick {_fmt(top, c.h)}: sellers rejected price here."))
            if bot - c.l >= WICK_FRAC * rng and not any(x.l <= c.l for x in later):
                zones.append(Zone("rejection", "bull", c.l, bot, c.t,
                                  f"Long lower wick {_fmt(c.l, bot)}: buyers rejected price here."))
    px = price if price is not None else cs[-1].c
    av = a[-1] or 0
    zones = [z for z in zones if (z.side == "bull" and z.low <= px) or (z.side == "bear" and z.high >= px)]
    near = [z for z in zones if av and (px - z.high if z.side == "bull" else z.low - px) <= near_atr * av]
    near.sort(key=lambda z: abs(px - (z.high if z.side == "bull" else z.low)))
    text = ("Nearby zones: " + " ".join(z.text for z in near[:3])) if near else "No unmitigated zones close to price."
    return ZoneSet(zones, near, text)
