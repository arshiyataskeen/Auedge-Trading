"""Walk-forward evaluation: do news models predict gold's post-release move better than the technical-only signal?

For every quarterly fold the harness fits each model on the rows before the fold (1-day embargo) and scores it on the
fold's rows. All metrics are computed on the pooled out-of-sample predictions. Nothing at or after a fold's start is
seen by any model, scaler, hyper-parameter search, temperature or stacker of that fold.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

import numpy as np

from . import metrics as M
from .data import CLASSES, Dataset
from .models import KNN, KNN_KS, LOGREG_CS, Bayes, Climatology, Forest, LogReg, TechnicalOnly, tune, tune_bayes
from .split import folds, inner_folds
from .stack import Stacker, vol_forecast
from .stats import bhattacharyya

MODEL_NAMES = ["Climatology", "TechnicalOnly", "Bayes", "KNN", "LogReg", "Forest"]
NEWS_CANDIDATES = ["Bayes", "KNN", "LogReg"]
DEFAULT_PRIMARY = "LogReg"
WARMUP_FOLDS = 2  # the first two folds have too little history to pick a primary model, so they use LogReg
CALIB_SHARE = 0.8  # temperature is fitted on the last 20 % of train, predicted by a model fitted on the first 80 %
GROUPS = ["NFP", "CPI", "FOMC", "other"]
N_EXAMPLES = 5
LABELS = ("label60", "label120")
T_MIN, T_MAX = float(M.TEMPERATURE_GRID[0]), float(M.TEMPERATURE_GRID[-1])  # T at an edge = search hit its limit


@dataclass
class Results:
    label: str
    n_rows: int  # rows in the dataset after applying the label
    n_test: int  # pooled out-of-sample rows
    fold_names: list[str]
    models: dict[str, dict]  # name -> {log_loss, brier, accuracy, n}
    per_kind: list[dict]  # {group, n, log_loss: {model: x}, diff_vs_tech: {model: (mean, lo, hi)}}
    per_fold: list[dict]  # {fold, n, primary, T, log_loss: {model: x}}
    reliability: dict[str, list]
    boot_vs_tech: dict[str, tuple[float, float, float]]  # model - TechnicalOnly per-row log-loss; negative = better
    forest_vs_logreg: tuple[float, float, float]  # pooled, after the fact: a diagnostic, not used for selection
    forest_kept: bool  # pooled diagnostic verdict of the keep rule (not used for selection)
    logreg_coefs: list[tuple[str, str, float]]
    knn_examples: list[dict]
    vol: dict
    go_live_forecast: bool
    best_news_model: str = ""
    primary_counts: dict[str, int] = field(default_factory=dict)
    forest_kept_per_fold: list[bool] = field(default_factory=list)  # the keep rule as actually used, past folds only
    stacker_probs: list[np.ndarray] = field(default_factory=list)  # per fold, test rows in fold order
    block_vs_tech: dict[str, tuple[float, float, float]] = field(default_factory=dict)  # same, fold-block bootstrap
    n_none_features: int = 0  # dataset rows whose stored features had a missing value (filled with 0)


def with_label(ds: Dataset, label: str) -> Dataset:
    """Dataset whose `y` is the requested label; for label120 rows without that label are dropped."""
    if label not in LABELS:
        raise ValueError(f"label must be one of {LABELS}")
    if label == "label60":
        return ds
    keep = np.flatnonzero(ds.y120 >= 0)
    return replace(ds, t=ds.t[keep], X=ds.X[keep], y=ds.y120[keep].copy(), y120=ds.y120[keep], kind=ds.kind[keep],
                   absmove60=ds.absmove60[keep], atr15=ds.atr15[keep],
                   move60=None if ds.move60 is None else ds.move60[keep])


RECENT_N = 40


def go_live(boot: tuple[float, float, float], block: tuple[float, float, float]) -> bool:
    """Go-live needs the stacker CI upper bound below 0 under BOTH the i.i.d. and the fold-block bootstrap."""
    return bool(boot[2] < 0 and block[2] < 0)


def vol_baselines(ds: Dataset, train: np.ndarray, test: np.ndarray) -> dict[str, np.ndarray]:
    """Volatility baselines for one fold, each learned from `train` rows only (dollars of |move60|).

    naive: train median |move60|; atr_only: train median of |move60|/atr15 x the row's atr15;
    recent40: median |move60| of the last 40 train releases.
    """
    train = np.sort(np.asarray(train))
    a = ds.atr15[train]
    ok = np.isfinite(a) & (a > 0)
    ratio = ds.absmove60[train][ok] / a[ok]
    atr_ratio = float(np.median(ratio)) if ok.any() else 0.0
    recent = train[-RECENT_N:]
    return {"naive": np.full(len(test), float(np.median(ds.absmove60[train]))),
            "atr_only": atr_ratio * ds.atr15[test],
            "recent40": np.full(len(test), float(np.median(ds.absmove60[recent])))}


def _vol_section(ds: Dataset, fs, test_idx: np.ndarray) -> dict:
    model = np.concatenate([vol_forecast(ds, f.train, f.test) for f in fs])
    bases = [vol_baselines(ds, f.train, f.test) for f in fs]
    preds = {"model": model, **{k: np.concatenate([b[k] for b in bases]) for k in ("naive", "atr_only", "recent40")}}
    actual, atr = ds.absmove60[test_idx], ds.atr15[test_idx]
    ok = np.isfinite(atr) & (atr > 0)  # rows without a usable ATR are left out of every volatility metric
    err = {k: np.abs(p[ok] - actual[ok]) for k, p in preds.items()}
    out = {"n": int(ok.sum()), "n_skipped": int((~ok).sum()),
           **{f"mae_{k}": float(e.mean()) for k, e in err.items()},
           "norm_mae": {k: float((e / atr[ok]).mean()) for k, e in err.items()}}
    for k in ("naive", "atr_only", "recent40"):
        out[f"boot_vs_{k}"] = M.paired_bootstrap(err["model"], err[k])
    kinds = np.array([_group(k) for k in ds.kind[test_idx]])[ok]
    out["per_kind"] = [{"group": g, "n": int((kinds == g).sum()), "mae_model": float(err["model"][kinds == g].mean()),
                        "mae_atr_only": float(err["atr_only"][kinds == g].mean())}
                       for g in GROUPS if (kinds == g).any()]
    return out


def _group(kind: str) -> str:
    return kind if kind in GROUPS[:3] else "other"


PARAM_ATTR = {"Bayes": "prior_strength", "KNN": "k", "LogReg": "C"}


def _param(model):
    """The tuned hyper-parameter of a fitted model (None for Forest, which is not tuned)."""
    attr = PARAM_ATTR.get(model.name)
    return getattr(model, attr) if attr else None


def _make(name: str, param):
    return {"Bayes": lambda: Bayes(param), "KNN": lambda: KNN(param), "LogReg": lambda: LogReg(param),
            "Forest": lambda: Forest()}[name]()


def _date(ts) -> str:
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d %H:%M")


def stack_fold(ds: Dataset, train: np.ndarray, test: np.ndarray, name: str, param, p_test: np.ndarray):
    """Calibrated stacker predictions for one fold. Returns (probs on test, temperature T, note).

    1. Temperature: fit the primary model (fixed hyper-parameter `param`) on the first 80 % of train, predict the
       last 20 %, and fit T on those predictions.
    2. Stacker training probabilities must not be in-sample, so they are out-of-fold predictions over train from the
       3 time-ordered inner folds (the primary model refitted on each inner train chunk). Train rows with no
       out-of-fold prediction (the first inner chunk) are dropped from the stacker's train.
    3. T is applied to the OOF probabilities and to `p_test` (the primary model fitted on ALL train); the Stacker is
       fitted on the calibrated OOF probabilities and predicts the test rows.
    The primary's hyper-parameter was tuned on the same inner chunks that supply the OOF rows, so the stacker's
    train probabilities are slightly optimistic (train-only optimism; nothing from the test fold is involved).
    If train is too short to give any OOF row, the stacker is skipped and the calibrated primary probabilities are
    returned, with a note saying so.
    """
    st, T, note = fit_stacker(ds, train, name, param)
    p_cal = M.apply_temperature(p_test, T)
    if st is None:
        return p_cal, T, note
    return st.predict_proba(ds, test, p_cal), T, ""


def fit_stacker(ds: Dataset, train: np.ndarray, name: str, param):
    """Temperature and fitted Stacker learned from `train` rows only (steps 1-3 of `stack_fold`).

    Returns (stacker or None, T, note); the stacker is None when train gives no out-of-fold row.
    """
    train = np.sort(train)
    cut = int(len(train) * CALIB_SHARE)
    fit_part, cal_part = train[:cut], train[cut:]
    T = 1.0
    if len(fit_part) and len(cal_part):
        T = M.fit_temperature(_make(name, param).fit(ds, fit_part).predict_proba(ds, cal_part), ds.y[cal_part])
    oof_idx, oof_p = [], []
    for tr, va in inner_folds(train):
        if len(tr) and len(va):
            oof_idx.append(va)
            oof_p.append(_make(name, param).fit(ds, tr).predict_proba(ds, va))
    if not oof_idx:
        return None, T, "no out-of-fold rows: stacker skipped, calibrated primary used"
    oof_idx, oof_p = np.concatenate(oof_idx), np.vstack(oof_p)
    return Stacker().fit(ds, oof_idx, M.apply_temperature(oof_p, T)), T, ""


def run(ds: Dataset, label: str = "label60", start: str = "2022-01-01") -> Results:
    """Walk-forward run of every model plus the stacker; see the module docstring."""
    ds = with_label(ds, label)
    fs = folds(ds.t, start)
    if not fs:
        raise ValueError("no walk-forward folds in the data")

    # Pass 1: every base model on every fold.
    fold_probs: list[dict[str, np.ndarray]] = []
    fitted: list[dict] = []
    for f in fs:
        ms = {"Climatology": Climatology().fit(ds, f.train), "TechnicalOnly": TechnicalOnly().fit(ds, f.train),
              "Bayes": tune_bayes(ds, f.train), "KNN": tune(KNN, KNN_KS, ds, f.train),
              "LogReg": tune(LogReg, LOGREG_CS, ds, f.train), "Forest": Forest().fit(ds, f.train)}
        fitted.append(ms)
        fold_probs.append({n: m.predict_proba(ds, f.test) for n, m in ms.items()})

    test_idx = np.concatenate([f.test for f in fs])
    y = ds.y[test_idx]
    pooled = {n: np.vstack([fp[n] for fp in fold_probs]) for n in MODEL_NAMES}
    row_ll = {n: M.row_log_loss(p, y) for n, p in pooled.items()}

    # Pooled random-forest comparison: after the fact, a diagnostic only (selection below uses past folds only).
    forest_vs_logreg = M.paired_bootstrap(row_ll["Forest"], row_ll["LogReg"])
    forest_kept = forest_vs_logreg[2] < 0

    # Pass 2: stacker. For fold i, the Forest keep rule (beats LogReg, paired-bootstrap 95 % CI entirely below 0)
    # and the primary model (lowest pooled log-loss) both use only the out-of-sample rows of folds before i.
    stack_p, per_fold, offsets = [], [], np.cumsum([0] + [len(f.test) for f in fs])
    primary_counts: dict[str, int] = {}
    kept_per_fold: list[bool] = []
    for i, f in enumerate(fs):
        past = slice(0, offsets[i])
        kept = i >= WARMUP_FOLDS and M.paired_bootstrap(row_ll["Forest"][past], row_ll["LogReg"][past])[2] < 0
        kept_per_fold.append(bool(kept))
        candidates = NEWS_CANDIDATES + (["Forest"] if kept else [])
        if i < WARMUP_FOLDS:
            primary = DEFAULT_PRIMARY
        else:
            primary = min(candidates, key=lambda n: (float(row_ll[n][past].mean()), candidates.index(n)))
        primary_counts[primary] = primary_counts.get(primary, 0) + 1
        p, T, note = stack_fold(ds, f.train, f.test, primary, _param(fitted[i][primary]), fold_probs[i][primary])
        stack_p.append(p)
        yf = ds.y[f.test]
        lls = {n: M.log_loss(fold_probs[i][n], yf) for n in MODEL_NAMES}
        lls["Stacker"] = M.log_loss(p, yf)
        per_fold.append({"fold": f.name, "n": int(len(f.test)), "primary": primary, "forest_kept": bool(kept),
                         "T": T, "T_edge": bool(T <= T_MIN + 1e-9 or T >= T_MAX - 1e-9), "note": note,
                         "log_loss": lls})
    pooled["Stacker"] = np.vstack(stack_p)
    row_ll["Stacker"] = M.row_log_loss(pooled["Stacker"], y)
    names = MODEL_NAMES + ["Stacker"]

    models = {n: {"log_loss": M.log_loss(pooled[n], y), "brier": M.brier(pooled[n], y),
                  "accuracy": M.accuracy(pooled[n], y), "n": int(len(y))} for n in names}
    boot = {n: M.paired_bootstrap(row_ll[n], row_ll["TechnicalOnly"]) for n in names if n != "TechnicalOnly"}
    reliab = {n: M.reliability(pooled[n], y) for n in names}

    groups = np.array([_group(k) for k in ds.kind[test_idx]])
    per_kind = []
    for g in GROUPS:
        m = groups == g
        if not m.any():
            continue
        per_kind.append({"group": g, "n": int(m.sum()),
                         "log_loss": {n: float(row_ll[n][m].mean()) for n in names},
                         "diff_vs_tech": {n: M.paired_bootstrap(row_ll[n][m], row_ll["TechnicalOnly"][m])
                                          for n in names if n != "TechnicalOnly"}})

    # Best single news model over all four news models: after the fact, not used by the stacker.
    after = NEWS_CANDIDATES + ["Forest"]
    best_news = min(after, key=lambda n: (models[n]["log_loss"], after.index(n)))

    # Volatility: bucketed |move60|/atr15 median x atr15, against naive / ATR-only / recent-window baselines.
    fold_of_row = np.concatenate([np.full(len(f.test), i) for i, f in enumerate(fs)])
    vol = _vol_section(ds, fs, test_idx)
    block = {n: M.block_bootstrap(row_ll[n], row_ll["TechnicalOnly"], fold_of_row) for n in names
             if n != "TechnicalOnly"}

    return Results(label=label, n_rows=int(len(ds.t)), n_test=int(len(y)), fold_names=[f.name for f in fs],
                   models=models, per_kind=per_kind, per_fold=per_fold, reliability=reliab, boot_vs_tech=boot,
                   forest_vs_logreg=forest_vs_logreg, forest_kept=bool(forest_kept),
                   logreg_coefs=fitted[-1]["LogReg"].coef_table(),
                   knn_examples=_knn_examples(ds, fs, fitted, test_idx), vol=vol,
                   go_live_forecast=go_live(boot["Stacker"], block["Stacker"]), best_news_model=best_news,
                   primary_counts=primary_counts, forest_kept_per_fold=kept_per_fold, stacker_probs=stack_p,
                   block_vs_tech=block, n_none_features=ds.n_none_features)


def _knn_examples(ds: Dataset, fs, fitted, test_idx) -> list[dict]:
    """The 5 largest |move60| test events with their fold's KNN neighbours, and how alike the neighbours' reactions
    are to all train rows of the same kind (Bhattacharyya distance of move60/atr15 histograms; diagnostic only)."""
    fold_of = {int(i): j for j, f in enumerate(fs) for i in f.test}
    move = ds.move60 if ds.move60 is not None else ds.absmove60
    zc, zm = ds.feature_names.index("z"), ds.feature_names.index("z_missing")

    def ratio(ix):
        a = ds.atr15[ix]
        return np.where(a > 0, move[ix] / np.where(a > 0, a, 1.0), 0.0)

    def fact(i):
        return {"date": _date(ds.t[i]), "kind": str(ds.kind[i]),
                "z": None if ds.X[i, zm] > 0.5 else float(ds.X[i, zc]), "move60": float(move[i]),
                "label": CLASSES[int(ds.y[i])]}

    order = sorted(test_idx.tolist(), key=lambda i: (-float(ds.absmove60[i]), i))[:N_EXAMPLES]
    out = []
    for i in order:
        j = fold_of[i]
        knn, train = fitted[j]["KNN"], fs[j].train
        nb = knn.neighbours(ds, i, train, knn.k)
        same_kind = train[ds.kind[train] == ds.kind[i]]
        bh = bhattacharyya(ratio(np.array(nb)), ratio(same_kind)) if len(same_kind) else float("nan")
        out.append({**fact(i), "fold": fs[j].name, "k": knn.k, "neighbours": [fact(n) for n in nb],
                    "bhattacharyya": bh})
    return out
