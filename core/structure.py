"""Market-structure tools shared by the agents: swings (zigzag), trend, BOS, liquidity, FVGs, sweeps.

All functions are deterministic and work on real OHLC candles (futures). Agents convert any price
they show to approximate spot with ctx.sp().
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from .indicators import atr, ema
from .models import Candle


@dataclass
class Pivot:
    i: int
    price: float
    kind: str              # "H" swing high, "L" swing low
    tentative: bool = False


def zigzag(candles: list[Candle], mult: float = 2.0) -> list[Pivot]:
    """Swing points: a new swing needs a reversal of at least `mult` x typical ATR."""
    n = len(candles)
    a = [x for x in atr(candles) if x]
    if n < 20 or not a:
        return []
    thr = mult * median(a)
    piv: list[Pivot] = []
    hi_i = lo_i = 0
    trend, ext = 0, 0
    for i in range(1, n):
        c = candles[i]
        if trend == 0:
            if c.h > candles[hi_i].h:
                hi_i = i
            if c.l < candles[lo_i].l:
                lo_i = i
            if candles[hi_i].h - candles[lo_i].l >= thr:
                if hi_i > lo_i:
                    piv.append(Pivot(lo_i, candles[lo_i].l, "L")); trend, ext = 1, hi_i
                else:
                    piv.append(Pivot(hi_i, candles[hi_i].h, "H")); trend, ext = -1, lo_i
        elif trend == 1:
            if c.h >= candles[ext].h:
                ext = i
            elif candles[ext].h - c.l >= thr:
                piv.append(Pivot(ext, candles[ext].h, "H")); trend, ext = -1, i
        else:
            if c.l <= candles[ext].l:
                ext = i
            elif c.h - candles[ext].l >= thr:
                piv.append(Pivot(ext, candles[ext].l, "L")); trend, ext = 1, i
    if trend:
        k = "H" if trend == 1 else "L"
        piv.append(Pivot(ext, candles[ext].h if k == "H" else candles[ext].l, k, tentative=True))
    return piv


def confirmed(piv: list[Pivot]) -> list[Pivot]:
    return [p for p in piv if not p.tentative]


def highs(piv): return [p for p in confirmed(piv) if p.kind == "H"]
def lows(piv): return [p for p in confirmed(piv) if p.kind == "L"]


def trend_state(piv: list[Pivot]) -> str:
    """UP (higher highs + higher lows), DOWN (lower highs + lower lows) or RANGE."""
    h, l = highs(piv)[-2:], lows(piv)[-2:]
    if len(h) < 2 or len(l) < 2:
        return "RANGE"
    hh, hl = h[1].price > h[0].price, l[1].price > l[0].price
    return "UP" if hh and hl else "DOWN" if not hh and not hl else "RANGE"


def run_count(points: list[Pivot], lower: bool) -> int:
    """How many consecutive lower (or higher) swings at the end of the list."""
    k = 0
    for a, b in zip(points[-2::-1], points[::-1]):
        if (b.price < a.price) == lower:
            k += 1
        else:
            break
    return k


def last_bos(candles: list[Candle], piv: list[Pivot]):
    """Most recent break of structure: (bar index, "UP"/"DOWN", broken level) or None."""
    events = []
    for p in confirmed(piv):
        for j in range(p.i + 1, len(candles)):
            if p.kind == "H" and candles[j].c > p.price:
                events.append((j, "UP", p.price)); break
            if p.kind == "L" and candles[j].c < p.price:
                events.append((j, "DOWN", p.price)); break
    return max(events) if events else None


def untouched(candles: list[Candle], piv: list[Pivot]) -> tuple[list[float], list[float]]:
    """Liquidity never traded through since it formed: (BSL above highs, SSL below lows)."""
    bsl, ssl = [], []
    for p in confirmed(piv):
        after = candles[p.i + 1:]
        if not after:
            continue
        if p.kind == "H" and max(c.h for c in after) < p.price:
            bsl.append(p.price)
        if p.kind == "L" and min(c.l for c in after) > p.price:
            ssl.append(p.price)
    return sorted(bsl), sorted(ssl, reverse=True)


def fvgs(candles: list[Candle], lookback: int = 60) -> list[tuple[str, float, float]]:
    """Unfilled fair-value gaps: (kind, bottom, top)."""
    out, n = [], len(candles)
    for i in range(max(2, n - lookback), n):
        a, c = candles[i - 2], candles[i]
        after = candles[i + 1:]
        if c.l > a.h and (not after or min(x.l for x in after) > a.h):
            out.append(("bull", a.h, c.l))
        if c.h < a.l and (not after or max(x.h for x in after) < a.l):
            out.append(("bear", c.h, a.l))
    return out


def sweep(candles: list[Candle], lookback: int = 20, recent: int = 15):
    """Most recent liquidity sweep: ("spring", level, idx) = wick below prior lows then close back
    above; ("upthrust", level, idx) = wick above prior highs then close back below."""
    n = len(candles)
    for j in range(n - 1, max(lookback, n - recent) - 1, -1):
        prior = candles[j - lookback:j]
        lo, hi = min(c.l for c in prior), max(c.h for c in prior)
        if candles[j].l < lo and candles[j].c > lo:
            return ("spring", lo, j)
        if candles[j].h > hi and candles[j].c < hi:
            return ("upthrust", hi, j)
    return None


def tf_bias(candles: list[Candle], mult: float = 2.0) -> dict:
    """Bias of one timeframe from swings + EMA50 + latest BOS."""
    piv = zigzag(candles, mult)
    closes = [c.c for c in candles]
    e50 = ema(closes, 50)[-1] if len(closes) >= 50 else None
    state = trend_state(piv)
    bos = last_bos(candles, piv)
    recent_bos = bos and bos[0] >= len(candles) - 12
    score = {"UP": 1, "DOWN": -1, "RANGE": 0}[state]
    if e50:
        score += 0.5 if closes[-1] > e50 else -0.5
    if recent_bos:
        score += 1 if bos[1] == "UP" else -1
    bias = "BUY" if score >= 1.5 else "SELL" if score <= -1.5 else "BUY lean" if score > 0 else \
        "SELL lean" if score < 0 else "RANGE"
    return {"bias": bias, "score": score, "state": state, "pivots": piv, "bos": bos,
            "recent_bos": bool(recent_bos), "ema50": e50}
