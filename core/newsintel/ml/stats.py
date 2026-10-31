"""Descriptive statistics of the 60-minute reaction, and a histogram distance used as a diagnostic."""
from __future__ import annotations

import numpy as np

from .data import CLASSES, PRIORITY, Dataset

BUCKETS = ["z_missing", "z<=-1", "mid", "z>=1"]
QUANTILES = (25, 50, 75, 90)


def _bucket(z: float, missing: bool) -> str:
    if missing:
        return "z_missing"
    return "z<=-1" if z <= -1 else ("z>=1" if z >= 1 else "mid")


def describe(ds: Dataset, idx) -> list[dict]:
    """One row per kind x surprise bucket (non-empty only): n, move60 mean/median/sd, class shares, |move60| quantiles."""
    if ds.move60 is None:
        raise ValueError("dataset has no signed move60")
    idx = np.asarray(idx)
    zc, mc = ds.feature_names.index("z"), ds.feature_names.index("z_missing")
    keys = [(ds.kind[i], _bucket(ds.X[i, zc], ds.X[i, mc] > 0.5)) for i in idx]
    present = {key[0] for key in keys}
    kinds = [k for k in PRIORITY if k in present] + sorted(present - set(PRIORITY))
    out = []
    for kind in kinds:
        for b in BUCKETS:
            sel = idx[[key == (kind, b) for key in keys]]
            if not len(sel):
                continue
            m, am, y = ds.move60[sel], np.abs(ds.move60[sel]), ds.y[sel]
            row = {"kind": kind, "bucket": b, "n": int(len(sel)), "mean": float(m.mean()),
                   "median": float(np.median(m)), "sd": float(m.std(ddof=1)) if len(sel) > 1 else 0.0}
            for c in ("up", "down", "side"):
                row[f"p_{c}"] = float(np.mean(y == CLASSES.index(c)))
            for q in QUANTILES:
                row[f"q{q}"] = float(np.percentile(am, q))
            out.append(row)
    return out


def bhattacharyya(a: np.ndarray, b: np.ndarray, bins: np.ndarray = np.linspace(-3, 3, 13)) -> float:
    """Distance -ln(BC) between two samples' Laplace-smoothed histograms (e.g. move60/atr15). 0 means identical."""
    def hist(x):
        x = np.clip(np.asarray(x, dtype=np.float64), bins[0], bins[-1])
        h = np.histogram(x, bins=bins)[0] + 1.0
        return h / h.sum()
    bc = float(np.sum(np.sqrt(hist(a) * hist(b))))
    return float(-np.log(min(bc, 1.0)))
