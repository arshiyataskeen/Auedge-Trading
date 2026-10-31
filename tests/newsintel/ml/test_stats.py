"""Descriptive stats and Bhattacharyya distance."""
from __future__ import annotations

import numpy as np
import pytest

from core.newsintel.ml import stats
from core.newsintel.ml.data import CLASSES, FEATURE_NAMES, Dataset

I = {n: i for i, n in enumerate(FEATURE_NAMES)}
D, S, U = (CLASSES.index(c) for c in ("down", "side", "up"))


def test_bhattacharyya_identical_symmetric_shifted():
    rng = np.random.default_rng(0)
    x = rng.normal(size=200)
    y = rng.normal(size=200) + 1.5
    assert stats.bhattacharyya(x, x) == pytest.approx(0.0, abs=1e-12)
    assert stats.bhattacharyya(x, y) == pytest.approx(stats.bhattacharyya(y, x))
    assert stats.bhattacharyya(x, y) > 0.05
    assert stats.bhattacharyya(np.array([]), x) >= 0  # empty sample is fine (Laplace)


def make():
    z = np.array([2.0, 1.0, 0.0, -1.0, 0.5, 0.0, 0.0])
    zm = np.array([0, 0, 0, 0, 0, 1, 1.0])
    X = np.zeros((7, len(FEATURE_NAMES)))
    X[:, I["z"]] = z
    X[:, I["z_missing"]] = zm
    kind = np.array(["CPI", "CPI", "CPI", "CPI", "NFP", "FOMC", "FOMC"])
    move = np.array([4.0, 2.0, 1.0, -3.0, 5.0, -1.0, 1.0])
    y = np.array([U, U, S, D, U, S, S])
    return Dataset(np.arange(7, dtype=np.int64), X, y, y.copy(), kind, np.abs(move), np.ones(7),
                   list(FEATURE_NAMES), move)


def test_describe_counts_and_moments():
    ds = make()
    rows = stats.describe(ds, np.arange(7))
    by = {(r["kind"], r["bucket"]): r for r in rows}
    assert sum(r["n"] for r in rows) == 7
    assert set(by) == {("CPI", "z>=1"), ("CPI", "mid"), ("CPI", "z<=-1"), ("NFP", "mid"), ("FOMC", "z_missing")}
    hi = by[("CPI", "z>=1")]
    assert hi["n"] == 2 and hi["mean"] == pytest.approx(3.0) and hi["median"] == pytest.approx(3.0)
    assert hi["sd"] == pytest.approx(np.std([4.0, 2.0], ddof=1))
    assert hi["p_up"] == 1.0 and hi["p_down"] == 0.0 and hi["p_side"] == 0.0
    assert hi["q50"] == pytest.approx(3.0)
    fomc = by[("FOMC", "z_missing")]
    assert fomc["n"] == 2 and fomc["p_side"] == 1.0 and fomc["mean"] == pytest.approx(0.0)
    assert by[("CPI", "z<=-1")]["p_down"] == 1.0


def test_describe_respects_idx():
    ds = make()
    rows = stats.describe(ds, np.array([0, 1]))
    assert len(rows) == 1 and rows[0]["n"] == 2


def test_describe_requires_signed_move():
    ds = make()
    ds.move60 = None
    with pytest.raises(ValueError):
        stats.describe(ds, np.arange(7))
