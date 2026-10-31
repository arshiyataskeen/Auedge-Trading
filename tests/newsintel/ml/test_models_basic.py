"""Baselines and Bayes: valid probabilities even with missing classes or kinds; climatology is smoothed frequencies."""
from __future__ import annotations

import numpy as np
import pytest

from core.newsintel.ml.data import CLASSES, FEATURE_NAMES, PRIORITY, Dataset
from core.newsintel.ml import models

DOWN, SIDE, UP = (CLASSES.index(c) for c in ("down", "side", "up"))
I = {n: i for i, n in enumerate(FEATURE_NAMES)}


def make_ds(kinds, y, z=None, trend=None, pre=None):
    n = len(y)
    rng = np.random.default_rng(0)
    X = np.zeros((n, len(FEATURE_NAMES)))
    X[:, I["z"]] = rng.normal(size=n) if z is None else z
    X[:, I["z_missing"]] = 0.0
    X[:, I["trend_score"]] = rng.normal(size=n) * 0.3 if trend is None else trend
    X[:, I["pre_range_atr15"]] = rng.random(n) * 3 if pre is None else pre
    y = np.asarray(y, dtype=np.int64)
    return Dataset(np.arange(n, dtype=np.int64) * 86400, X, y, y.copy(), np.array(kinds, dtype=str),
                   np.abs(rng.normal(size=n)), np.ones(n), list(FEATURE_NAMES), rng.normal(size=n))


def check_probs(p, n):
    assert p.shape == (n, 3)
    assert np.all(np.isfinite(p)) and np.all(p > 0)
    assert np.allclose(p.sum(axis=1), 1.0)


def all_models():
    return [models.Climatology(), models.TechnicalOnly(), models.Bayes(5.0)]


@pytest.mark.parametrize("model", all_models(), ids=lambda m: m.name)
def test_fit_with_a_missing_class_predicts_3_probs(model):
    n = 40
    y = [UP if i % 2 else DOWN for i in range(n)]  # no "side" in train
    ds = make_ds(["CPI"] * n, y + [], trend=np.linspace(-1, 1, n))
    model.fit(ds, np.arange(30))
    p = model.predict_proba(ds, np.arange(30, n))
    check_probs(p, 10)
    assert np.all(p[:, SIDE] > 0)


@pytest.mark.parametrize("model", all_models(), ids=lambda m: m.name)
def test_unseen_kind_still_valid(model):
    n = 30
    y = [i % 3 for i in range(n)]
    kinds = ["CPI"] * 20 + ["GDP"] * 10
    ds = make_ds(kinds, y)
    model.fit(ds, np.arange(20))  # GDP never seen in train
    check_probs(model.predict_proba(ds, np.arange(20, 30)), 10)


def test_climatology_is_per_kind_smoothed_frequency():
    kinds = ["NFP"] * 10 + ["CPI"] * 4
    y = [UP] * 6 + [DOWN] * 3 + [SIDE] + [UP] * 4
    ds = make_ds(kinds, y)
    m = models.Climatology().fit(ds, np.arange(14))
    p = m.predict_proba(ds, np.array([0, 10]))
    assert p[0] == pytest.approx(np.array([3 + 1, 1 + 1, 6 + 1]) / 13)
    assert p[1] == pytest.approx(np.array([0 + 1, 0 + 1, 4 + 1]) / 7)


def test_bayes_huge_prior_strength_matches_climatology():
    # every kind has the same class mix, so pooled and per-kind frequencies coincide
    rng = np.random.default_rng(1)
    kinds = ["NFP", "CPI"] * 60
    y = np.repeat(np.tile([UP, UP, DOWN, SIDE, UP, DOWN], 10), 2)
    ds = make_ds(kinds, y, z=rng.normal(size=120), trend=rng.normal(size=120) * 0.3)
    idx = np.arange(120)
    clim = models.Climatology().fit(ds, idx).predict_proba(ds, idx)
    bay = models.Bayes(1e9).fit(ds, idx).predict_proba(ds, idx)
    assert np.allclose(clim, bay, atol=0.02)


def test_bayes_uses_evidence_when_prior_weak():
    n = 300
    rng = np.random.default_rng(2)
    z = rng.normal(size=n)
    y = np.where(z >= 1, UP, np.where(z <= -1, DOWN, SIDE))
    ds = make_ds(["CPI"] * n, y, z=z)
    m = models.Bayes(2.0).fit(ds, np.arange(n))
    probe = make_ds(["CPI"] * 2, [UP, DOWN], z=np.array([2.0, -2.0]))
    p = m.predict_proba(probe, np.arange(2))
    assert p[0].argmax() == UP and p[1].argmax() == DOWN


def test_technical_only_uses_trend_and_scaler_fit_on_train_only():
    n = 200
    trend = np.linspace(-1, 1, n)
    y = np.where(trend > 0.3, UP, np.where(trend < -0.3, DOWN, SIDE))
    ds = make_ds(["CPI"] * n, y, trend=trend)
    m = models.TechnicalOnly().fit(ds, np.arange(0, n, 2))
    p = m.predict_proba(ds, np.array([5, 195]))
    assert p[0].argmax() == DOWN and p[1].argmax() == UP
    # scaler sees train rows only
    train = np.arange(0, 100)
    ds2 = make_ds(["CPI"] * n, y, trend=np.where(np.arange(n) >= 100, trend * 1000, trend))
    m2 = models.TechnicalOnly().fit(ds2, train)
    assert m2.scaler_.mean_[0] == pytest.approx(ds2.X[train, I["trend_score"]].mean())


def test_tune_bayes_picks_grid_value_and_predicts():
    n = 240
    rng = np.random.default_rng(3)
    z = rng.normal(size=n)
    y = np.where(z >= 1, UP, np.where(z <= -1, DOWN, SIDE))
    ds = make_ds(["CPI"] * n, y, z=z)
    m = models.tune_bayes(ds, np.arange(180))
    assert m.prior_strength in models.PRIOR_STRENGTHS
    check_probs(m.predict_proba(ds, np.arange(180, n)), 60)


def test_deterministic():
    n = 100
    y = [i % 3 for i in range(n)]
    ds = make_ds(["CPI"] * n, y)
    a = models.TechnicalOnly().fit(ds, np.arange(80)).predict_proba(ds, np.arange(80, n))
    b = models.TechnicalOnly().fit(ds, np.arange(80)).predict_proba(ds, np.arange(80, n))
    assert np.array_equal(a, b)
