"""Stacker (technical + news log-odds) and the volatility forecast. Both learn from train rows only."""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from .data import Dataset
from .models import N_CLASSES, _counts, _to_classes

MIN_BUCKET = 5
Z_EDGE = 1.0


class Stacker:
    """Multinomial LR on [trend_score, log(p_up/p_down), log(p_side/p_down)] of the primary model's calibrated probs.

    `p` passed to fit/predict_proba is the primary model's probabilities aligned row-for-row with `idx`.
    """

    name = "Stacker"

    @staticmethod
    def _features(ds: Dataset, idx: np.ndarray, p: np.ndarray) -> np.ndarray:
        col = ds.feature_names.index("trend_score")
        lp = np.log(np.clip(np.asarray(p, dtype=np.float64), 1e-15, 1.0))
        return np.column_stack([ds.X[idx, col], lp[:, 2] - lp[:, 0], lp[:, 1] - lp[:, 0]])

    def fit(self, ds: Dataset, idx, p: np.ndarray) -> "Stacker":
        idx = np.asarray(idx)
        x = self._features(ds, idx, p)
        y = ds.y[idx]
        self.scaler_ = StandardScaler().fit(x)
        self.single_ = len(np.unique(y)) < 2
        if self.single_:
            self.fallback_ = _counts(y) + 1.0
        else:
            self.lr_ = LogisticRegression(C=1.0, max_iter=2000, random_state=0)
            self.lr_.fit(self.scaler_.transform(x), y)
        return self

    def predict_proba(self, ds: Dataset, idx, p: np.ndarray) -> np.ndarray:
        idx = np.asarray(idx)
        if self.single_:
            return np.tile(self.fallback_ / self.fallback_.sum(), (len(idx), 1))
        raw = self.lr_.predict_proba(self.scaler_.transform(self._features(ds, idx, p)))
        return _to_classes(raw, self.lr_.classes_)


def vol_forecast(ds: Dataset, train_idx, test_idx) -> np.ndarray:
    """|move60| forecast = train median of |move60|/atr15 for the (kind, |z|>=1) bucket x the row's atr15.

    A bucket with < 5 train rows falls back to the kind's median, then to the overall train median.
    Rows with a missing surprise count as |z| < 1.
    """
    tr, te = np.asarray(train_idx), np.asarray(test_idx)
    az, zm = ds.feature_names.index("abs_z"), ds.feature_names.index("z_missing")

    def big(ix):
        return (ds.X[ix, az] >= Z_EDGE) & (ds.X[ix, zm] < 0.5)

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = ds.absmove60[tr] / ds.atr15[tr]
    ok = np.isfinite(ratio)
    overall = float(np.median(ratio[ok])) if ok.any() else 0.0
    kinds_tr, big_tr = ds.kind[tr], big(tr)

    def med(mask):
        m = mask & ok
        return float(np.median(ratio[m])) if m.sum() >= MIN_BUCKET else None

    cache: dict[tuple, float] = {}
    out = np.empty(len(te))
    big_te = big(te)
    for i, (k, b) in enumerate(zip(ds.kind[te], big_te)):
        key = (k, bool(b))
        if key not in cache:
            kind_mask = kinds_tr == k
            m = med(kind_mask & (big_tr == b))
            if m is None:
                m = med(kind_mask)
            cache[key] = overall if m is None else m
        out[i] = cache[key] * ds.atr15[te[i]]
    return out
