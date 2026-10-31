"""Baseline and Bayes models. Every model returns an (n, 3) array of probabilities in CLASSES order.

A model only ever learns from the rows in `idx` given to `fit`, so a walk-forward fold never leaks the future.
A class or kind missing from train still gets a small positive probability.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from .data import CLASSES, Dataset
from .split import inner_folds

N_CLASSES = len(CLASSES)
ABSENT = 1e-6
PRIOR_STRENGTHS = (2.0, 5.0, 10.0, 20.0)
Z_EDGE = 1.0
TREND_EDGE = 0.15


class Model(Protocol):
    name: str

    def fit(self, ds: Dataset, idx) -> "Model": ...

    def predict_proba(self, ds: Dataset, idx) -> np.ndarray: ...


def _counts(y: np.ndarray) -> np.ndarray:
    return np.bincount(y, minlength=N_CLASSES).astype(np.float64)[:N_CLASSES]


def _log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-15, 1.0)
    return float(-np.mean(np.log(p[np.arange(len(y)), y])))


class Climatology:
    """Per-kind class frequencies from train, Laplace +1. A kind never seen in train uses the pooled frequencies."""

    name = "Climatology"

    def fit(self, ds: Dataset, idx) -> "Climatology":
        idx = np.asarray(idx)
        self.pooled_ = _counts(ds.y[idx]) + 1.0
        self.by_kind_ = {k: _counts(ds.y[idx[ds.kind[idx] == k]]) + 1.0 for k in np.unique(ds.kind[idx])}
        return self

    def predict_proba(self, ds: Dataset, idx) -> np.ndarray:
        c = np.array([self.by_kind_.get(k, self.pooled_) for k in ds.kind[np.asarray(idx)]]).reshape(-1, N_CLASSES)
        return c / c.sum(axis=1, keepdims=True)


class TechnicalOnly:
    """Multinomial logistic regression on the single trend_score column; scaler fitted on train rows only."""

    name = "TechnicalOnly"

    def fit(self, ds: Dataset, idx) -> "TechnicalOnly":
        idx = np.asarray(idx)
        self.col_ = ds.feature_names.index("trend_score")
        x = ds.X[idx][:, [self.col_]]
        self.scaler_ = StandardScaler().fit(x)
        self.lr_ = LogisticRegression(C=1.0, max_iter=1000, random_state=0)
        y = ds.y[idx]
        self.single_ = len(np.unique(y)) < 2
        if self.single_:
            self.fallback_ = _counts(y) + 1.0
        else:
            self.lr_.fit(self.scaler_.transform(x), y)
        return self

    def predict_proba(self, ds: Dataset, idx) -> np.ndarray:
        idx = np.asarray(idx)
        if self.single_:
            return np.tile(self.fallback_ / self.fallback_.sum(), (len(idx), 1))
        raw = self.lr_.predict_proba(self.scaler_.transform(ds.X[idx][:, [self.col_]]))
        p = np.full((len(idx), N_CLASSES), ABSENT)
        p[:, self.lr_.classes_] = raw
        return p / p.sum(axis=1, keepdims=True)


class Bayes:
    """Dirichlet-multinomial naive Bayes over three binned facts: surprise bucket, trend state, pre-release range.

    Prior: pooled class counts give a Dirichlet of total weight `prior_strength`, updated with each kind's own counts.
    Each evidence bin's likelihood per class is smoothed towards the pooled bin frequency with the same strength.
    A large strength therefore collapses to the pooled class frequencies.
    """

    name = "Bayes"

    def __init__(self, prior_strength: float = 5.0):
        self.prior_strength = float(prior_strength)

    def _bins(self, ds: Dataset, idx: np.ndarray) -> np.ndarray:
        X = ds.X[idx]
        f = ds.feature_names.index
        z, miss = X[:, f("z")], X[:, f("z_missing")] > 0.5
        surprise = np.where(miss, 0, np.where(z <= -Z_EDGE, 1, np.where(z < Z_EDGE, 2, 3)))
        tr = X[:, f("trend_score")]
        trend = np.where(tr < -TREND_EDGE, 0, np.where(tr <= TREND_EDGE, 1, 2))
        vol = np.searchsorted(self.vol_edges_, X[:, f("pre_range_atr15")], side="right")
        return np.stack([surprise, trend, vol], axis=1)

    def fit(self, ds: Dataset, idx) -> "Bayes":
        idx = np.asarray(idx)
        s = self.prior_strength
        f = ds.feature_names.index("pre_range_atr15")
        self.vol_edges_ = np.quantile(ds.X[idx, f], [1 / 3, 2 / 3]) if len(idx) else np.zeros(2)
        y = ds.y[idx]
        self.pooled_prior_ = (_counts(y) + 1.0) / (len(y) + N_CLASSES)
        self.kind_counts_ = {k: _counts(y[ds.kind[idx] == k]) for k in np.unique(ds.kind[idx])}
        bins = self._bins(ds, idx)
        cls_n = _counts(y)
        self.like_ = []  # per feature: (n_bins, 3) likelihoods P(bin | class)
        for j, nb in enumerate((4, 3, 3)):
            q = np.bincount(bins[:, j], minlength=nb) + 1.0
            q = q / q.sum()
            cnt = np.zeros((nb, N_CLASSES))
            for c in range(N_CLASSES):
                cnt[:, c] = np.bincount(bins[y == c, j], minlength=nb)
            self.like_.append((cnt + s * q[:, None]) / (cls_n[None, :] + s))
        return self

    def predict_proba(self, ds: Dataset, idx) -> np.ndarray:
        idx = np.asarray(idx)
        s = self.prior_strength
        zero = np.zeros(N_CLASSES)
        prior = np.array([(self.kind_counts_.get(k, zero) + s * self.pooled_prior_)
                          / (self.kind_counts_.get(k, zero).sum() + s) for k in ds.kind[idx]])
        logp = np.log(prior.reshape(-1, N_CLASSES))
        bins = self._bins(ds, idx)
        for j, like in enumerate(self.like_):
            logp = logp + np.log(like[bins[:, j]])
        logp -= logp.max(axis=1, keepdims=True)
        p = np.exp(logp)
        return p / p.sum(axis=1, keepdims=True)


def tune_bayes(ds: Dataset, train_idx, grid=PRIOR_STRENGTHS) -> Bayes:
    """Pick prior_strength with the lowest mean log-loss over the inner time-ordered folds, then refit on all train."""
    train_idx = np.asarray(train_idx)
    best, best_loss = grid[0], np.inf
    for s in grid:
        losses = [_log_loss(Bayes(s).fit(ds, tr).predict_proba(ds, va), ds.y[va])
                  for tr, va in inner_folds(train_idx) if len(tr) and len(va)]
        loss = float(np.mean(losses)) if losses else np.inf
        if loss < best_loss:
            best, best_loss = s, loss
    return Bayes(best).fit(ds, train_idx)
