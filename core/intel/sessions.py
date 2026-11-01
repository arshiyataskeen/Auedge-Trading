"""One shared session helper: Asian / London / New York / overlap windows in New York time (DST-safe).

All windows are NY wall-clock hours converted with ZoneInfo. Only CLOSED candles are used: a candle that
starts at t is closed once t + tf <= now.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
ASIAN = (20, 24)        # evening NY, ends at midnight NY (ICT convention)
LONDON = (3, 12)
NEWYORK = (8, 17)
OVERLAP = (8, 12)
LOW_LIQUIDITY = (17, 19)


def ny(t) -> datetime:
    return datetime.fromtimestamp(t, timezone.utc).astimezone(NY)


def _wall(d, hour: int) -> int:
    """Unix time of NY wall-clock `hour` (24 = next midnight) on date d."""
    if hour == 24:
        d, hour = d + timedelta(days=1), 0
    return int(datetime.combine(d, time(hour), tzinfo=NY).timestamp())


@dataclass
class SessionNow:
    sessions: list[str]
    low_liquidity: bool
    text: str


@dataclass
class SessionRange:
    name: str
    high: float
    low: float
    start: int
    end: int
    bars: int
    text: str


@dataclass
class OpenSweep:
    open_name: str       # "London open" | "New York open"
    swept: str           # which range was swept, e.g. "Asian high"
    side: str            # "buy" (buy-side liquidity above taken) | "sell"
    t: int
    price: float
    text: str


def current_sessions(t) -> SessionNow:
    h = ny(t).hour
    names = []
    if h >= ASIAN[0]:
        names.append("Asian")
    if LONDON[0] <= h < LONDON[1]:
        names.append("London")
    if NEWYORK[0] <= h < NEWYORK[1]:
        names.append("New York")
    if OVERLAP[0] <= h < OVERLAP[1]:
        names.append("London/New York overlap")
    low = LOW_LIQUIDITY[0] <= h < LOW_LIQUIDITY[1]
    txt = ("Active: " + ", ".join(names) + ".") if names else "Between sessions, quiet."
    if low:
        txt = "Low-liquidity window (17:00-19:00 New York): thin, erratic trading."
    return SessionNow(names, low, txt)


def window_range(candles, start: int, end: int, now_t=None, tf: int = 900, min_bars: int = 1):
    """(high, low, bars) of closed candles with start <= t < end, or None when fewer than min_bars."""
    lim = end if now_t is None else min(end, now_t - tf + 1)
    bars = [c for c in candles if start <= c.t < lim and (now_t is None or c.t + tf <= now_t)]
    if len(bars) < min_bars:
        return None
    return max(c.h for c in bars), min(c.l for c in bars), len(bars)


def asian_window(now_t, mode: str = "ny_evening") -> tuple[int, int]:
    """Window of the latest Asian session. mode 'ny_evening' = 20:00-00:00 NY ending at the latest NY midnight
    (what agents/ict.py always used); 'utc_0_7' = 00:00-07:00 UTC of today (what core/liquidity.py used)."""
    if mode == "utc_0_7":
        d0 = datetime.fromtimestamp(now_t, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(d0.timestamp()), int(d0.timestamp()) + 7 * 3600
    today = ny(now_t).date()
    return _wall(today - timedelta(days=1), 20), _wall(today, 0)


def asian_range(candles, now_t, mode: str = "ny_evening", min_bars: int = 1, tf: int = 900):
    """(high, low) of the latest finished Asian window, or None (not finished yet / too few bars)."""
    s, e = asian_window(now_t, mode)
    if now_t < e:
        return None
    r = window_range(candles, s, e, None, tf, min_bars)
    return (r[0], r[1]) if r else None


def session_range(candles, name: str, now_t, tf: int = 900) -> SessionRange | None:
    """Range of the latest Asian / London / New York session that has started (closed candles only)."""
    hrs = {"Asian": ASIAN, "London": LONDON, "New York": NEWYORK}[name]
    today = ny(now_t).date()
    for back in (0, 1, 2, 3, 4):
        d = today - timedelta(days=back)
        a, b = _wall(d - timedelta(days=1) if name == "Asian" else d, hrs[0]), _wall(d if name == "Asian" else d, hrs[1])
        if a > now_t:
            continue
        r = window_range(candles, a, b, now_t, tf)
        if r:
            return SessionRange(name, r[0], r[1], a, b, r[2],
                                f"{name} session range {r[1]:.2f} to {r[0]:.2f} ({r[2]} bars).")
    return None


def open_sweeps(candles, now_t, tf: int = 900) -> list[OpenSweep]:
    """London open (03:00 NY) taking the Asian range, New York open (08:00 NY) taking the London pre-open range:
    a closed candle pokes beyond the range and closes back inside it."""
    today = ny(now_t).date()
    out: list[OpenSweep] = []
    plans = (("London open", _wall(today, 3), _wall(today, 5), asian_window(now_t)[0], _wall(today, 3), "Asian"),
             ("New York open", _wall(today, 8), _wall(today, 10), _wall(today, 3), _wall(today, 8), "London"))
    for oname, o0, o1, r0, r1, rname in plans:
        if now_t < o0:
            continue
        r = window_range(candles, r0, r1, now_t, tf)
        if not r:
            continue
        hi, lo, _ = r
        for c in candles:
            if not (o0 <= c.t < o1 and c.t + tf <= now_t):
                continue
            if c.h > hi and c.c < hi:
                out.append(OpenSweep(oname, f"{rname} high", "buy", c.t, hi,
                                     f"At the {oname} price poked above the {rname} high {hi:.2f} and closed back below it: a liquidity grab."))
            if c.l < lo and c.c > lo:
                out.append(OpenSweep(oname, f"{rname} low", "sell", c.t, lo,
                                     f"At the {oname} price poked below the {rname} low {lo:.2f} and closed back above it: a liquidity grab."))
    return out
