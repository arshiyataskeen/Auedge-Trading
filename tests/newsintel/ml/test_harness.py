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


def test_go_live_requires_both_cis():
    assert harness.go_live((-0.1, -0.2, -0.01), (-0.1, -0.3, -0.02)) is True
    assert harness.go_live((-0.1, -0.2, -0.01), (-0.1, -0.3, 0.05)) is False
    assert harness.go_live((-0.1, -0.2, 0.01), (-0.1, -0.3, -0.02)) is False


def test_results_go_live_uses_both_cis(res):
    assert res.go_live_forecast == harness.go_live(res.boot_vs_tech["Stacker"], res.block_vs_tech["Stacker"])
    assert set(res.block_vs_tech) == set(res.boot_vs_tech)


def test_vol_baselines_use_train_rows_only():
    ds = synth()
    f = harness.folds(ds.t)[1]
    before = harness.vol_baselines(ds, f.train, f.test)
    ds.absmove60[f.test] = ds.absmove60[f.test] * 100 + 7
    after = harness.vol_baselines(ds, f.train, f.test)
    assert set(before) == {"naive", "atr_only", "recent40"}
    for k in before:
        assert np.array_equal(before[k], after[k])
    ds.absmove60[f.train] = ds.absmove60[f.train] + 5
    changed = harness.vol_baselines(ds, f.train, f.test)
    assert all(not np.array_equal(before[k], changed[k]) for k in before)


def test_vol_baselines_recent40_is_last_forty_train_rows():
    ds = synth()
    f = harness.folds(ds.t)[2]
    tr = np.sort(f.train)
    expect = float(np.median(ds.absmove60[tr[-40:]]))
    assert np.all(harness.vol_baselines(ds, f.train, f.test)["recent40"] == expect)


def test_vol_section_fields_and_skips_bad_atr():
    ds = synth()
    ds.atr15[::50] = 0.0  # unusable ATR on some rows
    r = harness.run(ds)
    v = r.vol
    assert v["n_skipped"] > 0 and v["n"] + v["n_skipped"] == r.n_test
    for k in ("mae_model", "mae_naive", "mae_atr_only", "mae_recent40"):
        assert np.isfinite(v[k]) and v[k] >= 0
    for k in ("naive", "atr_only", "recent40"):
        lo, hi = v[f"boot_vs_{k}"][1:]
        assert lo <= hi
    assert set(v["norm_mae"]) == {"model", "naive", "atr_only", "recent40"}
    assert {g["group"] for g in v["per_kind"]} <= {"NFP", "CPI", "FOMC", "other"}
    assert "left out" in report.verdict_lines(r)[-1]


def test_verdict_says_plain_atr_scaling_when_ci_includes_zero(res):
    import copy
    r = copy.deepcopy(res)
    r.vol["boot_vs_atr_only"] = (-0.1, -0.5, 0.3)
    line = report.verdict_lines(r)[-1]
    assert "Volatility: the news buckets add nothing measurable over plain ATR scaling (" in line
    r.vol["boot_vs_atr_only"] = (-0.5, -0.9, -0.1)
    assert "plain ATR scaling" in report.verdict_lines(r)[-1]
    assert "add nothing measurable" not in report.verdict_lines(r)[-1]


def test_verdict_and_html_show_both_cis_baselines_and_data_note(res, tmp_path):
    lines = report.verdict_lines(res)
    assert "i.i.d. bootstrap" in lines[0] and "fold-block bootstrap" in lines[0]
    assert any(s.startswith("Data note:") for s in lines)
    html = report.write(res, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "ATR-only" in html and "recent-40" in html and "missing stored feature" in html


def test_dataset_none_feature_count_flows_to_results():
    ds = synth()
    ds.n_none_features = 7
    assert harness.run(ds).n_none_features == 7
