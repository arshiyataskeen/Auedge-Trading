"""Walk-forward harness and report: deterministic, honest go-live check, per-kind n, readable verdict."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from core.newsintel.ml import harness, report
from core.newsintel.ml.data import CLASSES, FEATURE_NAMES, PRIORITY, Dataset

I = {n: i for i, n in enumerate(FEATURE_NAMES)}
DOWN, SIDE, UP = (CLASSES.index(c) for c in ("down", "side", "up"))
KINDS = ["NFP", "CPI", "FOMC", "CLAIMS", "PPI"]


def synth(n=300, random_labels=False, seed=0) -> Dataset:
    """300 releases over 2021-2022; z drives the label unless random_labels."""
    rng = np.random.default_rng(seed)
    t0 = int(datetime(2021, 1, 4, tzinfo=timezone.utc).timestamp())
    t = t0 + (np.arange(n) * (730 * 86400 // n)).astype(np.int64)
    kinds = np.array([KINDS[i % len(KINDS)] for i in range(n)])
    z = rng.normal(size=n) * 1.5
    X = np.zeros((n, len(FEATURE_NAMES)))
    X[:, I["z"]] = z
    X[:, I["abs_z"]] = np.abs(z)
    for i, k in enumerate(kinds):
        X[i, I[f"kind_{k}"]] = 1.0
    atr = rng.random(n) + 1.0
    X[:, I["atr15"]] = atr
    X[:, I["atr1h"]] = atr * 2
    X[:, I["pre_range_atr15"]] = rng.random(n) * 3
    X[:, I["trend_score"]] = rng.normal(size=n) * 0.3
    X[:, I["hours_since_prev"]] = rng.random(n) * 168
    X[:, I["n_releases"]] = 1.0
    if random_labels:
        y = rng.integers(0, 3, n)
    else:
        noisy = z + rng.normal(size=n) * 0.3
        y = np.where(noisy > 0.6, UP, np.where(noisy < -0.6, DOWN, SIDE))
    move = np.where(y == UP, 1.0, np.where(y == DOWN, -1.0, 0.1)) * atr * (1 + np.abs(z))
    return Dataset(t, X, y.astype(np.int64), y.astype(np.int64).copy(), kinds, np.abs(move), atr,
                   list(FEATURE_NAMES), move)


@pytest.fixture(scope="module")
def res():
    return harness.run(synth())


def _numbers(r: harness.Results):
    return (r.models, r.per_kind, r.per_fold, r.boot_vs_tech, r.vol, r.forest_vs_logreg, r.logreg_coefs,
            [(e["date"], e["neighbours"], e["bhattacharyya"]) for e in r.knn_examples])


def test_harness_is_deterministic(res):
    assert _numbers(res) == _numbers(harness.run(synth()))


def test_logreg_beats_technical_and_go_live(res):
    assert res.models["LogReg"]["log_loss"] < res.models["TechnicalOnly"]["log_loss"]
    assert res.go_live_forecast is True
    assert res.boot_vs_tech["Stacker"][2] < 0


@pytest.mark.parametrize("seed", range(5))
def test_random_labels_fail_go_live(seed):
    assert harness.run(synth(random_labels=True, seed=seed)).go_live_forecast is False


def test_last_fold_labels_do_not_change_earlier_folds(res):
    ds = synth()
    last = harness.folds(ds.t)[-1].test
    ds.y[last] = (ds.y[last] + 1) % 3
    ds.y120[last] = ds.y[last]
    other = harness.run(ds)
    for a, b in zip(res.stacker_probs[:-1], other.stacker_probs[:-1]):
        assert np.array_equal(a, b)
    assert res.forest_kept_per_fold[:-1] == other.forest_kept_per_fold[:-1]
    assert [f["primary"] for f in res.per_fold[:-1]] == [f["primary"] for f in other.per_fold[:-1]]


def test_forest_keep_decided_from_previous_folds_only(res):
    assert len(res.forest_kept_per_fold) == len(res.fold_names)
    assert res.forest_kept_per_fold[:2] == [False, False]


def test_stack_fold_without_oof_rows_falls_back():
    ds = synth()
    train, test = np.arange(1), np.arange(2, 6)  # one train row: inner folds give no out-of-fold rows
    p_test = np.full((4, 3), 1 / 3)
    p, T, note = harness.stack_fold(ds, train, test, "LogReg", 1.0, p_test)
    assert p.shape == (4, 3) and np.allclose(p.sum(axis=1), 1.0) and note


def test_per_fold_flags_temperature_at_grid_edge(res):
    for f in res.per_fold:
        assert f["T_edge"] == (f["T"] <= 0.25 + 1e-9 or f["T"] >= 4.0 - 1e-9)


def test_per_kind_table_includes_n(res):
    groups = {row["group"]: row for row in res.per_kind}
    assert set(groups) == {"NFP", "CPI", "FOMC", "other"}
    assert all(row["n"] > 0 for row in res.per_kind)
    assert sum(row["n"] for row in res.per_kind) == res.n_test
    assert "Stacker" in groups["NFP"]["log_loss"]


def test_results_shape(res):
    assert [f["fold"] for f in res.per_fold] == ["2022Q1", "2022Q2", "2022Q3", "2022Q4"]
    assert [f["primary"] for f in res.per_fold[:2]] == ["LogReg", "LogReg"]
    for name in harness.MODEL_NAMES + ["Stacker"]:
        assert name in res.models and name in res.reliability
    assert len(res.knn_examples) == 5
    assert all(len(e["neighbours"]) > 0 for e in res.knn_examples)
    assert res.logreg_coefs and isinstance(res.forest_kept, bool)
    assert res.vol["mae_model"] > 0 and res.vol["mae_naive"] > 0


def test_label120_uses_y120_and_drops_missing():
    ds = synth()
    ds.y120[:20] = -1
    ds.y120[20:] = (ds.y[20:] + 1) % 3
    r = harness.run(ds, label="label120")
    assert r.label == "label120" and r.n_rows == len(ds.t) - 20


def test_report_has_verdict_and_every_model(res, tmp_path):
    path = report.write(res, tmp_path / "r.html")
    html = path.read_text(encoding="utf-8")
    assert "Verdict" in html
    for name in harness.MODEL_NAMES + ["Stacker"]:
        assert name in html
    lines = report.verdict_lines(res)
    assert lines[0].startswith("News intelligence does beat the technical-only signal")
    assert any("(chosen after the fact; not used by the stacker)" in s for s in lines)
    assert "after the fact, not used for selection" in html


def test_failed_check_recommends_risk_only(tmp_path):
    r = harness.run(synth(random_labels=True, seed=3))
    lines = report.verdict_lines(r)
    assert lines[0].startswith("News intelligence does not beat the technical-only signal")
    assert any("Recommended use: risk only (volatility expectation and AVOID gates), not direction." in s for s in lines)
