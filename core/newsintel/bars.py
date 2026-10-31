"""Helpers for reading 1-minute candles: price at a time, time windows, resampling.

Every function only uses finished candles (a candle starting at t is finished at t + its
length), so nothing here peeks at the future relative to the `x` / `end` it is given.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from core.models import Candle
from core.newsintel.minutes import Minutes

NY = ZoneInfo("America/New_York")
STALE_SEC = 30 * 60


def price_at(m: Minutes, x: int) -> float | None:
    """Close of the last finished minute at time x; None if there is none or it is stale."""
    i = int(np.searchsorted(m.t, x - 60, side="right")) - 1  # last t with t + 60 <= x
    if i < 0 or x - (int(m.t[i]) + 60) > STALE_SEC:
        return None
    return float(m.c[i])


def window(m: Minutes, a: int, b: int) -> slice:
    """Slice of the candles with a <= t < b."""
    return slice(int(np.searchsorted(m.t, a, side="left")), int(np.searchsorted(m.t, b, side="left")))


def _candle(m: Minutes, s: slice, t: int) -> Candle:
    return Candle(t=t, o=float(m.o[s.start]), h=float(m.h[s].max()),
                  l=float(m.l[s].min()), c=float(m.c[s.stop - 1]))


def resample(m: Minutes, sec: int, end: int, n: int) -> list[Candle]:
    """The last n finished `sec`-second candles (buckets t // sec * sec) ending at or before `end`.

    Buckets with no minutes are skipped, so fewer than n may come back near the data's start.
    """
    if n <= 0:
        return []
    stop = end // sec * sec  # buckets starting before this are finished
    hi = int(np.searchsorted(m.t, stop, side="left"))
    span = n * sec * 2
    while True:  # widen the look-back until n buckets are found or the data runs out
        lo = int(np.searchsorted(m.t, stop - span, side="left"))
        buckets = m.t[lo:hi] // sec
        starts = np.flatnonzero(np.diff(buckets, prepend=-1) != 0)
        if len(starts) >= n + 1 or lo == 0:
            break
        span *= 2
    bounds = list(starts) + [hi - lo]
    out = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        out.append(_candle(m, slice(lo + a, lo + b), int(buckets[a]) * sec))
    return out[-n:]


def session_day_candles(m: Minutes, end: int, n: int) -> list[Candle]:
    """The last n daily candles by gold session (18:00 -> 17:00 New York, named by the end day).

    A session is finished once 17:00 NY of its day is <= end. The candle's t is 00:00 NY of
    that day. Days with no data (weekends) are skipped.
    """
    if n <= 0 or len(m.t) == 0:
        return []
    d = datetime.fromtimestamp(end, NY).date()
    if end < int(datetime(d.year, d.month, d.day, 17, tzinfo=NY).timestamp()):
        d -= timedelta(days=1)  # today's session is still forming
    first = int(m.t[0])
    out: list[Candle] = []
    while len(out) < n:
        prev = d - timedelta(days=1)
        start = int(datetime(prev.year, prev.month, prev.day, 18, tzinfo=NY).timestamp())
        # market is closed 17:00-18:00; never include a minute not finished by `end`
        stop = min(int(datetime(d.year, d.month, d.day, 17, tzinfo=NY).timestamp()), end - 59)
        if stop <= first:
            break
        s = window(m, start, stop)
        if s.stop > s.start:
            out.append(_candle(m, s, int(datetime(d.year, d.month, d.day, tzinfo=NY).timestamp())))
        d = prev
    return out[::-1]
