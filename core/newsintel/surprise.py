"""Surprise proxy: how far a release landed from what its own history predicts.

There is no consensus forecast in the data, so the expectation for each release comes
from an AR(1) fit on strictly earlier first releases (expanding window). With too little
history it falls back to the last value. Nothing after release i is ever used for i.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.newsintel.fred import Release


@dataclass
class Surprise:
    """Expected value, its error scale and the signed z-score (positive = hawkish / strong USD)."""
    release_date: str
    expected: float | None
    sigma: float | None
    z: float | None


def _expect(history: list[float], min_ar: int) -> tuple[float | None, float | None]:
    n = len(history)
    if n >= min_ar and n >= 4:
        y = np.asarray(history, dtype=float)
        x = np.column_stack([np.ones(n - 1), y[:-1]])
        coef, *_ = np.linalg.lstsq(x, y[1:], rcond=None)
        resid = y[1:] - x @ coef
        return float(coef[0] + coef[1] * y[-1]), float(np.std(resid, ddof=2))
    if n >= 3:
        return history[-1], float(np.std(np.diff(history), ddof=1))
    return None, None


def expectations(releases: list[Release], sign: int, min_ar: int = 24) -> list[Surprise]:
    """One Surprise per release, same order; release i sees only releases 0..i-1."""
    out: list[Surprise] = []
    actuals = [r.actual for r in releases]
    for i, r in enumerate(releases):
        exp, sigma = _expect(actuals[:i], min_ar)
        z = None
        if exp is not None and sigma:  # None or 0 -> no z
            z = sign * (r.actual - exp) / sigma
        out.append(Surprise(r.release_date, exp, sigma, z))
    return out
