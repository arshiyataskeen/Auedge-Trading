"""Metrics, reliability, bootstrap and temperature scaling."""
from __future__ import annotations

import numpy as np
import pytest

from core.newsintel.ml import metrics as m


def test_log_loss_perfect_and_uniform():
    y = np.array([0, 1, 2, 1])
    assert m.log_loss(np.eye(3)[y], y) < 1e-10
    assert abs(m.log_loss(np.full((4, 3), 1 / 3), y) - np.log(3)) < 1e-12


def test_brier_uniform_and_perfect():
    y = np.array([0, 1, 2])
    assert abs(m.brier(np.full((3, 3), 1 / 3), y) - 2 / 3) < 1e-12
    assert m.brier(np.eye(3)[y], y) == 0.0


def test_accuracy():
    p = np.array([[0.6, 0.3, 0.1], [0.1, 0.2, 0.7]])
    assert m.accuracy(p, np.array([0, 1])) == 0.5


def test_reliability_bins():
    p = np.array([[0.9, 0.05, 0.05], [0.9, 0.05, 0.05], [0.4, 0.3, 0.3]])
    r = m.reliability(p, np.array([0, 1, 0]))
    assert [n for _, _, n in r] == [1, 2]
    assert abs(r[0][0] - 0.4) < 1e-12 and r[0][1] == 1.0
    assert abs(r[1][0] - 0.9) < 1e-12 and r[1][1] == 0.5


def test_bootstrap_identical_is_zero():
    a = np.random.default_rng(0).random(50)
    assert m.paired_bootstrap(a, a.copy()) == (0.0, 0.0, 0.0)


def test_bootstrap_ci_and_determinism():
    rng = np.random.default_rng(0)
    b = rng.random(200)
    a = b - 0.5
    mean, lo, hi = m.paired_bootstrap(a, b)
    assert abs(mean + 0.5) < 1e-12 and lo <= mean <= hi and hi < 0
    assert m.paired_bootstrap(a, b) == (mean, lo, hi)


def test_temperature_overconfident_gives_T_above_1():
    rng = np.random.default_rng(0)
    n = 600
    y = rng.integers(0, 3, n)
    p = np.full((n, 3), 0.02)
    guess = np.where(rng.random(n) < 0.5, y, rng.integers(0, 3, n))  # ~67% right, but claims 96%
    p[np.arange(n), guess] = 0.96
    T = m.fit_temperature(p, y)
    assert T > 1
    assert m.log_loss(m.apply_temperature(p, T), y) < m.log_loss(p, y)


def test_apply_temperature_identity_and_rows_sum_to_1():
    p = np.array([[0.2, 0.3, 0.5], [0.7, 0.2, 0.1]])
    assert np.allclose(m.apply_temperature(p, 1.0), p)
    assert np.allclose(m.apply_temperature(p, 2.0).sum(axis=1), 1.0)


def test_vol_mae():
    assert m.vol_mae(np.array([1.0, 3.0]), np.array([2.0, 1.0])) == 1.5


def test_block_bootstrap_identical_is_zero():
    a = np.linspace(0, 1, 20)
    assert m.block_bootstrap(a, a.copy(), np.repeat([0, 1, 2, 3], 5)) == (0.0, 0.0, 0.0)


def test_block_bootstrap_singleton_groups_match_iid():
    rng = np.random.default_rng(1)
    a, b = rng.normal(size=60) + 0.3, rng.normal(size=60)
    mean, lo, hi = m.block_bootstrap(a, b, np.arange(60))
    imean, ilo, ihi = m.paired_bootstrap(a, b)
    assert mean == pytest.approx(imean)
    assert lo == pytest.approx(ilo, abs=0.05) and hi == pytest.approx(ihi, abs=0.05)
    assert m.block_bootstrap(a, b, np.arange(60)) == (mean, lo, hi)


def test_block_bootstrap_wider_than_iid_for_clustered_losses():
    # 4 groups of 50 rows; each group has its own offset (regime) so rows within a group are correlated.
    rng = np.random.default_rng(2)
    offsets = np.array([-0.4, -0.3, -0.2, 0.5])
    groups = np.repeat(np.arange(4), 50)
    d = offsets[groups] + rng.normal(size=200) * 0.05  # mean ~ -0.1, but driven by 3 of 4 regimes
    a, b = d, np.zeros(200)
    _, _, ihi = m.paired_bootstrap(a, b)
    _, _, bhi = m.block_bootstrap(a, b, groups)
    assert ihi < 0 < bhi
