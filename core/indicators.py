"""Plain-Python technical indicators (no external libraries)."""
from __future__ import annotations

from statistics import pstdev

from .models import Candle


def sma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes: list[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    out[n] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def atr(candles: list[Candle], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(candles)
    if len(candles) <= n:
        return out
    trs = [candles[0].h - candles[0].l]
    for i in range(1, len(candles)):
        c, pc = candles[i], candles[i - 1].c
        trs.append(max(c.h - c.l, abs(c.h - pc), abs(c.l - pc)))
    prev = sum(trs[1:n + 1]) / n
    out[n] = prev
    for i in range(n + 1, len(candles)):
        prev = (prev * (n - 1) + trs[i]) / n
        out[i] = prev
    return out


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    ef, es = ema(closes, fast), ema(closes, slow)
    line = [f - s if f is not None and s is not None else None for f, s in zip(ef, es)]
    valid = [x for x in line if x is not None]
    sig_valid = ema(valid, signal)
    sig: list[float | None] = [None] * (len(line) - len(valid)) + sig_valid
    hist = [l - s if l is not None and s is not None else None for l, s in zip(line, sig)]
    return line, sig, hist


def bollinger(closes: list[float], n: int = 20, k: float = 2.0):
    mid = sma(closes, n)
    upper: list[float | None] = [None] * len(closes)
    lower: list[float | None] = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        sd = pstdev(closes[i - n + 1:i + 1])
        upper[i], lower[i] = mid[i] + k * sd, mid[i] - k * sd
    return mid, upper, lower


def swings(candles: list[Candle], left: int = 2, right: int = 2) -> tuple[list[float], list[float]]:
    """Fractal swing highs and lows."""
    highs, lows = [], []
    for i in range(left, len(candles) - right):
        win = candles[i - left:i + right + 1]
        if candles[i].h == max(c.h for c in win):
            highs.append(candles[i].h)
        if candles[i].l == min(c.l for c in win):
            lows.append(candles[i].l)
    return highs, lows


def cluster(levels: list[float], tol: float) -> list[tuple[float, int]]:
    """Merge nearby levels; returns (average price, touches)."""
    groups: list[list[float]] = []
    for lv in sorted(levels):
        if groups and lv - groups[-1][-1] <= tol:
            groups[-1].append(lv)
        else:
            groups.append([lv])
    return [(sum(g) / len(g), len(g)) for g in groups]


def last(values: list, back: int = 0):
    """Value `back` steps from the end, or None."""
    return values[-1 - back] if len(values) > back else None


def clamp(x: float, lo: float = 0, hi: float = 100) -> int:
    return int(max(lo, min(hi, round(x))))
