"""Scoring, calibration and paired bootstrap. Probabilities are (n, 3) in CLASSES order; y holds class indices."""
from __future__ import annotations

import numpy as np

N_CLASSES = 3
CLIP = 1e-15
TEMPERATURE_GRID = np.linspace(0.25, 4.0, 76)


def row_log_loss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Per-row negative log-likelihood of the true class (probabilities clipped at 1e-15)."""
    p = np.clip(np.asarray(p, dtype=np.float64), CLIP, 1.0)
    return -np.log(p[np.arange(len(y)), np.asarray(y, dtype=int)])


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean(row_log_loss(p, y)))


def row_brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    onehot = np.eye(N_CLASSES)[np.asarray(y, dtype=int)]
    return ((np.asarray(p, dtype=np.float64) - onehot) ** 2).sum(axis=1)


def brier(p: np.ndarray, y: np.ndarray) -> float:
    """Multi-class Brier: sum of squared errors over the 3 classes, averaged over rows."""
    return float(np.mean(row_brier(p, y)))


def accuracy(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean(np.argmax(p, axis=1) == np.asarray(y)))


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[tuple[float, float, int]]:
    """(mean confidence, frequency correct, n) per non-empty bin of the max probability over [1/3, 1]."""
    p = np.asarray(p, dtype=np.float64)
    conf = p.max(axis=1)
    hit = (np.argmax(p, axis=1) == np.asarray(y)).astype(np.float64)
    lo = 1.0 / N_CLASSES
    b = np.clip(((conf - lo) / (1.0 - lo) * bins).astype(int), 0, bins - 1)
    out = []
    for k in range(bins):
        m = b == k
        if m.any():
            out.append((float(conf[m].mean()), float(hit[m].mean()), int(m.sum())))
    return out


def paired_bootstrap(loss_a: np.ndarray, loss_b: np.ndarray, n: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Resample rows with replacement; returns (mean of a-b, 2.5th pct, 97.5th pct). Negative means a is better."""
    d = np.asarray(loss_a, dtype=np.float64) - np.asarray(loss_b, dtype=np.float64)
    rng = np.random.default_rng(seed)
    means = d[rng.integers(0, len(d), size=(n, len(d)))].mean(axis=1)
    return float(d.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def apply_temperature(p: np.ndarray, T: float) -> np.ndarray:
    """Soften (T>1) or sharpen (T<1) probabilities: softmax(log p / T)."""
    z = np.log(np.clip(np.asarray(p, dtype=np.float64), CLIP, 1.0)) / T
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def fit_temperature(p: np.ndarray, y: np.ndarray) -> float:
    """Grid-search T in [0.25, 4] (76 points) for the lowest log-loss; ties go to the smaller T."""
    losses = [log_loss(apply_temperature(p, T), y) for T in TEMPERATURE_GRID]
    return float(TEMPERATURE_GRID[int(np.argmin(losses))])


def vol_mae(pred: np.ndarray, actual: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(pred) - np.asarray(actual))))
