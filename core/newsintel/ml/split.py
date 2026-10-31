"""Walk-forward splits: test on one calendar quarter, train on everything before it (1-day embargo).

Nothing at or after a fold's start can reach training, so models never see the future.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

DAY = 86400
FULL_QUARTER_SLACK = 7 * DAY  # a quarter counts as full if the data reaches within a week of its end


@dataclass
class Fold:
    name: str  # e.g. "2022Q3"
    train: np.ndarray  # row indices
    test: np.ndarray


def _ts(y: int, m: int) -> int:
    return int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp())


def folds(t: np.ndarray, start: str = "2022-01-01") -> list[Fold]:
    """Quarterly test folds from `start` to the last full quarter in the data."""
    t = np.asarray(t)
    if len(t) == 0:
        return []
    d = datetime.strptime(start, "%Y-%m-%d")
    y, q = d.year, (d.month - 1) // 3
    last = int(t.max())
    out: list[Fold] = []
    while True:
        a = _ts(y, q * 3 + 1)
        y2, q2 = (y + 1, 0) if q == 3 else (y, q + 1)
        b = _ts(y2, q2 * 3 + 1)
        if last < b - FULL_QUARTER_SLACK:
            break
        test = np.flatnonzero((t >= a) & (t < b))
        train = np.flatnonzero(t < a - DAY)
        if len(test):
            out.append(Fold(f"{y}Q{q + 1}", train, test))
        y, q = y2, q2
    return out


def inner_folds(train_idx: np.ndarray, n: int = 3) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window inner folds inside a train set: split into n+1 time chunks, validate on chunk i+1."""
    idx = np.sort(np.asarray(train_idx))
    chunks = np.array_split(idx, n + 1)
    return [(np.concatenate(chunks[: i + 1]), chunks[i + 1]) for i in range(n)]
