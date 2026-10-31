"""Loads gold's 1-minute candles from the pg_dump backup into numpy arrays.

Parsing 2.3 million rows is slow, so the result is cached as a .npz file and reused
until the backup file changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from tools.pgdump_read import iter_copy_rows

DATA = Path(__file__).resolve().parent.parent.parent / "data"
TABLE = "public.ohlcv_xauusd"


@dataclass
class Minutes:
    """1-minute bid candles: epoch seconds `t` (sorted, unique) and open/high/low/close."""
    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray


def _from_npz(cache: Path) -> Minutes:
    z = np.load(cache)
    return Minutes(z["t"], z["o"], z["h"], z["l"], z["c"])


def load_backup_minutes(backup: Path, cache: Path = DATA / "news_intel" / "xau_1m.npz") -> Minutes:
    """Return the 1min candles from the backup; uses the cache if it is newer than the backup."""
    backup, cache = Path(backup), Path(cache)
    # cache wins when the backup is gone or older than it
    if cache.exists() and (not backup.exists() or cache.stat().st_mtime >= backup.stat().st_mtime):
        return _from_npz(cache)
    t, o, h, l, c = [], [], [], [], []
    for row in iter_copy_rows(backup, TABLE):
        # columns: symbol, granularity, ts, bid_open, bid_high, bid_low, bid_close, ask_close, volume
        if row[1] != "1min":
            continue
        t.append(int(datetime.fromisoformat(row[2]).timestamp()))
        o.append(float(row[3]))
        h.append(float(row[4]))
        l.append(float(row[5]))
        c.append(float(row[6]))
    ta = np.array(t, dtype=np.int64)
    ta, idx = np.unique(ta, return_index=True)  # sorts and drops duplicate minutes
    m = Minutes(ta, *(np.array(a, dtype=np.float64)[idx] for a in (o, h, l, c)))
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache, t=m.t, o=m.o, h=m.h, l=m.l, c=m.c)
    return m
