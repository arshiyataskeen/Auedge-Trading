"""Stacker and volatility forecast: valid probabilities, train-only learning."""
from __future__ import annotations

import numpy as np

from core.newsintel.ml.stack import Stacker, vol_forecast
from tests.newsintel.ml.test_models_basic import DOWN, SIDE, UP, check_probs, make_ds


def _ds(n=60):
    rng = np.random.default_rng(2)
    y = rng.integers(0, 3, n)
    ds = make_ds(["CPI" if i % 2 else "NFP" for i in range(n)], y)
    ds.X[:, ds.feature_names.index("abs_z")] = np.abs(ds.X[:, ds.feature_names.index("z")])
    ds.atr15 = rng.random(n) + 0.5
    ds.absmove60 = np.abs(ds.move60)
    return ds


def _probs(n, seed=0):
    p = np.random.default_rng(seed).random((n, 3)) + 0.1
    return p / p.sum(axis=1, keepdims=True)


def test_stacker_valid_probs():
    ds = _ds()
    p = _probs(60)
    s = Stacker().fit(ds, np.arange(40), p[:40])
    check_probs(s.predict_proba(ds, np.arange(40, 60), p[40:]), 20)


def test_stacker_missing_class_and_single_class():
    ds = _ds()
    p = _probs(60)
    ds.y[:40] = np.where(ds.y[:40] == SIDE, UP, ds.y[:40])
    check_probs(Stacker().fit(ds, np.arange(40), p[:40]).predict_proba(ds, np.arange(40, 60), p[40:]), 20)
    ds.y[:40] = DOWN
    check_probs(Stacker().fit(ds, np.arange(40), p[:40]).predict_proba(ds, np.arange(40, 60), p[40:]), 20)


def test_stacker_scaler_train_only():
    ds = _ds()
    p = _probs(60)
    a = Stacker().fit(ds, np.arange(40), p[:40])
    ds.X[40:] *= 1000
    b = Stacker().fit(ds, np.arange(40), p[:40])
    assert np.allclose(a.scaler_.mean_, b.scaler_.mean_)


def test_vol_forecast_uses_only_train_rows():
    ds = _ds()
    tr, te = np.arange(40), np.arange(40, 60)
    a = vol_forecast(ds, tr, te)
    ds.move60[te] *= 100
    ds.absmove60[te] *= 100
    assert np.array_equal(a, vol_forecast(ds, tr, te))


def test_vol_forecast_bucket_and_fallbacks():
    n = 30
    ds = _ds(n)
    ds.kind[:] = "CPI"
    ds.atr15[:] = 2.0
    ds.atr15[-1] = 4.0
    absz = ds.feature_names.index("abs_z")
    zm = ds.feature_names.index("z_missing")
    ds.X[:, absz] = 0.0
    ds.X[:10, absz] = 2.0          # 10 big rows, ratio 3
    ds.absmove60[:10] = 6.0
    ds.absmove60[10:29] = 2.0      # 19 small rows, ratio 1
    ds.X[27:29, absz] = 2.0        # 2 big rows in train beyond the first 10 (still big bucket)
    tr = np.arange(29)
    ds.X[29, absz] = 5.0
    out = vol_forecast(ds, tr, np.array([29]))
    assert out[0] == np.median(ds.absmove60[:29][ds.X[:29, absz] >= 1] / 2.0) * 4.0
    ds.X[29, zm] = 1.0             # missing z counts as small
    small = vol_forecast(ds, tr, np.array([29]))
    assert small[0] == 1.0 * 4.0
    # unseen kind -> overall median
    ds.kind[29] = "GDP"
    assert vol_forecast(ds, tr, np.array([29]))[0] == np.median(ds.absmove60[:29] / 2.0) * 4.0
    # sparse big bucket (<5) -> kind median
    ds.kind[29] = "CPI"
    ds.X[29, zm] = 0.0
    ds.X[:29, absz] = 0.0
    ds.X[:2, absz] = 2.0
    assert vol_forecast(ds, tr, np.array([29]))[0] == np.median(ds.absmove60[:29] / 2.0) * 4.0
