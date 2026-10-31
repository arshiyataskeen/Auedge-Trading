"""Surprise proxy: how far a release landed from what its own history predicts.

There is no consensus forecast in the data, so the expectation for each release comes
from an AR(1) fit on strictly earlier first releases (expanding window). With too little
history it falls back to the last value. Nothing after release i is ever used for i.

The error scale is a robust one (1.4826 x MAD of the last 36 residuals), and releases
for observation periods inside the COVID shock (2020-03 .. 2021-06) are left out of every
later fit and scale: otherwise those prints dominate sigma for years and mute every later z.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.newsintel.fred import Release

COVID = ("2020-03-01", "2021-06-30")  # observation dates excluded from fit and sigma history
N_RESID = 36       # residuals used for sigma
MIN_RESID = 12     # fewer than this -> fallback (last value, std of changes)
MAD_SCALE = 1.4826  # MAD -> standard deviation for normal errors
MIN_SIGMA = 1e-12


@dataclass
class Surprise:
    """Expected value, its error scale and the signed z-score (positive = hawkish / strong USD)."""
    release_date: str
    expected: float | None
    sigma: float | None
    z: float | None


def _expect(history: list[float], min_ar: int) -> tuple[float | None, float | None]:
    n = len(history)
    if n >= min_ar and n >= 4 and n - 1 >= MIN_RESID:
        y = np.asarray(history, dtype=float)
        x = np.column_stack([np.ones(n - 1), y[:-1]])
        coef, *_ = np.linalg.lstsq(x, y[1:], rcond=None)
        resid = (y[1:] - x @ coef)[-N_RESID:]
        mad = float(np.median(np.abs(resid - np.median(resid))))
        return float(coef[0] + coef[1] * y[-1]), MAD_SCALE * mad
    if n >= 3:
        return history[-1], float(np.std(np.diff(history), ddof=1))
    return None, None


def _usable(r: Release) -> bool:
    return r.actual is not None and not (COVID[0] <= r.obs_date <= COVID[1])


def expectations(releases: list[Release], sign: int, min_ar: int = 24) -> list[Surprise]:
    """One Surprise per release, same order; release i sees only releases 0..i-1.

    A release without an actual (missing prior period) gets no expectation and is skipped
    in later histories, as are releases for COVID-window periods.
    """
    out: list[Surprise] = []
    history: list[float] = []
    for r in releases:
        exp = sigma = z = None
        if r.actual is not None:
            exp, sigma = _expect(history, min_ar)
            if exp is not None and sigma is not None and sigma >= MIN_SIGMA:
                z = sign * (r.actual - exp) / sigma
        out.append(Surprise(r.release_date, exp, sigma, z))
        if _usable(r):
            history.append(r.actual)
    return out
