"""Fit the news models on all history once and save them (with live thresholds) for the live app.

`python -m core.newsintel.ml --export [--until YYYY-MM-DD]` writes `models.pkl` and `meta.json` to MODELS_DIR.
With `until`, only rows (and 1-minute candles) strictly before that date feed any stored number, so a later
holdout stays honest.
"""
from __future__ import annotations

import json
import pickle
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import harness
from .data import Dataset
from .models import KNN, KNN_KS, LOGREG_CS, Forest, LogReg, TechnicalOnly, tune, tune_bayes
from .split import folds
from .stack import Stacker, vol_tables
from .stats import bhattacharyya, describe
from ..minutes import DATA, Minutes, _from_npz

MODELS_DIR = DATA / "news_intel" / "models"
MINUTES_CACHE = DATA / "news_intel" / "xau_1m.npz"
PICKLE, META = "models.pkl", "meta.json"
UNCERTAIN_MAX_P_PCT = 20  # stacker confidence below this percentile of out-of-sample rows = "uncertain"
UNCERTAIN_BHATT_PCT = 80  # neighbours' reactions less alike than this percentile of out-of-sample rows = "uncertain"
M5_PCT = 99
M5_ATR_N = 14
EVENT_BEFORE, EVENT_AFTER = 30 * 60, 180 * 60  # seconds around an event that count as "event window"


@dataclass
class Artifacts:
    primary: object  # fitted news model (Bayes / KNN / LogReg / Forest), all rows
    primary_name: str
    stacker: Stacker
    technical: TechnicalOnly
    temperature: float
    vol_table: dict  # (kind, |z|>=1) -> median |move60|/atr15
    vol_kind: dict  # kind -> median
    vol_overall: float
    stats_rows: list
    neighbours_X: np.ndarray  # rows in the KNN's scaled space (kind columns weighted), one per dataset row
    neighbours_meta: dict  # arrays t, kind, z (nan if missing), move60, one per dataset row
    uncertain_max_p: float
    uncertain_bhatt: float
    m5_range_p99: float
    go_live: bool
    trained_through: str
    version: str
    knn: object = None  # KNN fitted on all rows: scales a live row into neighbours_X's space
    neighbour_k: int = 7
    trained_until: str | None = None


def _cut(until: str) -> int:
    return int(datetime.strptime(until, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def truncate(ds: Dataset, until: str) -> Dataset:
    """Rows with t < `until` (YYYY-MM-DD, UTC midnight)."""
    keep = np.flatnonzero(ds.t < _cut(until))
    return replace(ds, t=ds.t[keep], X=ds.X[keep], y=ds.y[keep], y120=ds.y120[keep], kind=ds.kind[keep],
                   absmove60=ds.absmove60[keep], atr15=ds.atr15[keep],
                   move60=None if ds.move60 is None else ds.move60[keep])


def choose_primary(res: harness.Results) -> str:
    """Forward choice for unseen rows: lowest pooled out-of-sample log-loss over all folds.

    Forest is a candidate only if it beat LogReg with the 95 % CI entirely below 0 (`res.forest_kept`).
    Ties go to the earlier candidate (Bayes, KNN, LogReg, Forest).
    """
    cands = harness.NEWS_CANDIDATES + (["Forest"] if res.forest_kept else [])
    return min(cands, key=lambda n: (res.models[n]["log_loss"], cands.index(n)))


def _ratio(ds: Dataset, ix) -> np.ndarray:
    a = ds.atr15[ix]
    return np.where(a > 0, ds.move60[ix] / np.where(a > 0, a, 1.0), 0.0)


def oos_bhattacharyya(ds: Dataset) -> np.ndarray:
    """Per out-of-sample row: Bhattacharyya distance between its fold-KNN neighbours' move60/atr15 and its kind's
    train rows' (the 'coherence' of similar past releases), in the harness's fold order."""
    out = []
    for f in folds(ds.t):
        knn = tune(KNN, KNN_KS, ds, f.train)
        sp_tr, sp_te = knn._space(ds, f.train), knn._space(ds, f.test)
        kind_tr = ds.kind[f.train]
        for r, i in enumerate(f.test):
            nb = f.train[np.argsort(np.linalg.norm(sp_tr - sp_te[r], axis=1), kind="stable")[:knn.k]]
            same = f.train[kind_tr == ds.kind[i]]
            out.append(bhattacharyya(_ratio(ds, nb), _ratio(ds, same)) if len(same) else np.nan)
    return np.array(out)


def _wilder_atr(tr: np.ndarray, n: int) -> np.ndarray:
    """ATR as core.indicators.atr: simple mean of the first n true ranges (from bar 1), then Wilder smoothing."""
    out = np.full(len(tr), np.nan)
    if len(tr) <= n:
        return out
    prev = tr[1:n + 1].mean()
    out[n] = prev
    for i in range(n + 1, len(tr)):
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


def m5_range_ratio(m: Minutes, event_times) -> np.ndarray:
    """(range of a 5-minute bar) / (Wilder ATR(14) of 5-minute bars up to and including it) for every bar outside
    every event window (30 min before to 180 min after an event time). Bars before the ATR exists are skipped."""
    b = m.t // 300
    starts = np.flatnonzero(np.diff(b, prepend=b[0] - 1) != 0)
    bt = b[starts] * 300
    hi, lo = np.maximum.reduceat(m.h, starts), np.minimum.reduceat(m.l, starts)
    cl = m.c[np.r_[starts[1:] - 1, len(m.t) - 1]]
    rng = hi - lo
    tr = rng.copy()
    tr[1:] = np.maximum(rng[1:], np.maximum(np.abs(hi[1:] - cl[:-1]), np.abs(lo[1:] - cl[:-1])))
    atr = _wilder_atr(tr, M5_ATR_N)
    near = np.zeros(len(bt), dtype=bool)
    for e in np.asarray(event_times, dtype=np.int64):
        near |= (bt + 300 > e - EVENT_BEFORE) & (bt < e + EVENT_AFTER)
    ok = ~near & np.isfinite(atr) & (atr > 0)
    return rng[ok] / atr[ok]


def export(ds: Dataset, out: Path = MODELS_DIR, until: str | None = None, minutes: Minutes | None = None) -> dict:
    """Run the harness on `ds` (label60), fit everything on all rows, write models.pkl + meta.json, return the meta."""
    if until is not None:
        ds = truncate(ds, until)
    res = harness.run(ds, "label60")
    if minutes is None:
        if not MINUTES_CACHE.exists():
            raise FileNotFoundError(f"1-minute history not found: {MINUTES_CACHE} (run python -m core.newsintel.build)")
        minutes = _from_npz(MINUTES_CACHE)
    if until is not None:
        k = int(np.searchsorted(minutes.t, _cut(until), side="left"))
        minutes = Minutes(*(a[:k] for a in (minutes.t, minutes.o, minutes.h, minutes.l, minutes.c)))

    alln = np.arange(len(ds.t))
    name = choose_primary(res)
    primary = {"Bayes": lambda: tune_bayes(ds, alln), "KNN": lambda: tune(KNN, KNN_KS, ds, alln),
               "LogReg": lambda: tune(LogReg, LOGREG_CS, ds, alln), "Forest": lambda: Forest().fit(ds, alln)}[name]()
    stacker, T, note = harness.fit_stacker(ds, alln, name, harness._param(primary))
    if stacker is None:
        raise ValueError(note)
    knn = tune(KNN, KNN_KS, ds, alln)
    table, by_kind, overall = vol_tables(ds, alln)
    zc, zm = ds.feature_names.index("z"), ds.feature_names.index("z_missing")
    meta_rows = {"t": ds.t.copy(), "kind": ds.kind.copy(), "move60": ds.move60.copy(),
                 "z": np.where(ds.X[:, zm] > 0.5, np.nan, ds.X[:, zc])}
    max_p = np.vstack(res.stacker_probs).max(axis=1)
    ratios = m5_range_ratio(minutes, ds.t)
    art = Artifacts(
        primary=primary, primary_name=name, stacker=stacker, technical=TechnicalOnly().fit(ds, alln),
        temperature=float(T), vol_table=table, vol_kind=by_kind, vol_overall=overall,
        stats_rows=describe(ds, alln), neighbours_X=knn._space(ds, alln), neighbours_meta=meta_rows,
        uncertain_max_p=float(np.percentile(max_p, UNCERTAIN_MAX_P_PCT)),
        uncertain_bhatt=float(np.nanpercentile(oos_bhattacharyya(ds), UNCERTAIN_BHATT_PCT)),
        m5_range_p99=float(np.percentile(ratios, M5_PCT)) if len(ratios) else float("nan"),
        go_live=bool(res.go_live_forecast),
        trained_through=datetime.fromtimestamp(int(ds.t[-1]), timezone.utc).strftime("%Y-%m-%d"),
        version=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        knn=knn, neighbour_k=knn.k, trained_until=until)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / PICKLE, "wb") as f:
        pickle.dump(art, f, protocol=5)
    meta = {"primary_name": art.primary_name, "temperature": art.temperature, "vol_overall": art.vol_overall,
            "uncertain_max_p": art.uncertain_max_p, "uncertain_bhatt": art.uncertain_bhatt,
            "m5_range_p99": art.m5_range_p99, "go_live": art.go_live, "trained_through": art.trained_through,
            "trained_until": until, "version": art.version, "n_rows": int(len(ds.t))}
    (out / META).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def load_artifacts(path: Path = MODELS_DIR) -> Artifacts | None:
    """The exported artifacts, or None when the export has never been run."""
    f = Path(path) / PICKLE
    if not f.exists():
        return None
    with open(f, "rb") as fh:
        return pickle.load(fh)
