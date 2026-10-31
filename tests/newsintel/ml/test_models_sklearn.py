"""KNN, LogReg, Forest: train-only scaling, valid probabilities, neighbours from train, tuning, determinism."""
from __future__ import annotations

import numpy as np

from core.newsintel.ml import models
from core.newsintel.ml.data import FEATURE_NAMES
from core.newsintel.ml.models import KNN, Forest, LogReg
from tests.newsintel.ml.test_models_basic import DOWN, SIDE, UP, check_probs, make_ds


def clusters(n=60):
    """Two separated clusters in z: negative z -> DOWN, positive z -> UP, interleaved in time."""
    rng = np.random.default_rng(1)
    y = np.array([DOWN if i % 2 else UP for i in range(n)])
    z = np.where(y == UP, 3.0, -3.0) + rng.normal(scale=0.3, size=n)
    return make_ds(["CPI"] * n, y, z=z, trend=np.zeros(n), pre=np.ones(n))


def test_scaler_fitted_on_train_only():
    ds = clusters()
    a = LogReg(1.0).fit(ds, np.arange(40))
    ds.X[40:] *= 1000
    b = LogReg(1.0).fit(ds, np.arange(40))
    assert np.allclose(a.scaler_.mean_, b.scaler_.mean_)
    k = KNN(5).fit(ds, np.arange(40))
    assert np.allclose(k.scaler_.mean_, a.scaler_.mean_)


def test_knn_separated_clusters():
    ds = clusters()
    p = KNN(5).fit(ds, np.arange(40)).predict_proba(ds, np.arange(40, 60))
    check_probs(p, 20)
    assert np.all(p[np.arange(20), ds.y[40:60]] >= 0.8)


def test_neighbours_come_from_train_idx():
    ds = clusters()
    tr = np.arange(0, 60, 2)
    m = KNN(5).fit(ds, tr)
    nb = m.neighbours(ds, 1, tr, 5)
    assert len(nb) == 5 and set(nb) <= set(tr.tolist())
    d = [np.linalg.norm(m._space(ds, [j]) - m._space(ds, [1])) for j in nb]
    assert d == sorted(d)


def test_missing_class_valid_for_all():
    n = 60
    y = [UP if i % 2 else DOWN for i in range(n)]
    ds = make_ds(["CPI"] * n, y, trend=np.linspace(-1, 1, n))
    for m in (KNN(5), LogReg(1.0), Forest(n_estimators=20)):
        p = m.fit(ds, np.arange(40)).predict_proba(ds, np.arange(40, 60))
        check_probs(p, 20)
        assert np.all(p[:, SIDE] > 0)


def test_single_class_train_logreg():
    ds = make_ds(["CPI"] * 20, [UP] * 20)
    check_probs(LogReg(1.0).fit(ds, np.arange(10)).predict_proba(ds, np.arange(10, 20)), 10)


def test_coef_table_rows():
    ds = clusters()
    ds.y[::5] = SIDE
    rows = LogReg(1.0).fit(ds, np.arange(60)).coef_table()
    assert len(rows) == 3 * len(FEATURE_NAMES)
    assert {r[0] for r in rows} == set(FEATURE_NAMES) and {r[1] for r in rows} == {"down", "side", "up"}


def test_tune_picks_expected_C_and_refits():
    ds = clusters(120)
    best = models.tune(LogReg, models.LOGREG_CS, ds, np.arange(120))
    assert isinstance(best, LogReg) and best.C in models.LOGREG_CS
    assert best.C > 0.1  # separable data: weaker regularisation beats the strongest
    assert best.predict_proba(ds, np.arange(5)).shape == (5, 3)


def test_forest_deterministic():
    ds = clusters()
    a = Forest(n_estimators=30).fit(ds, np.arange(40)).predict_proba(ds, np.arange(40, 60))
    b = Forest(n_estimators=30).fit(ds, np.arange(40)).predict_proba(ds, np.arange(40, 60))
    assert np.array_equal(a, b)
