"""Turns news_intel.db into model-ready arrays: one row per release time that has a complete 60-minute label.

Each row carries only facts known before the label window opens. When several releases share a time,
the highest-priority kind is the row's kind. Missing numbers become 0 (plus a z_missing flag for surprise).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import store

CLASSES = ["down", "side", "up"]
PRIORITY = ["FOMC", "NFP", "CPI", "PCE", "PPI", "GDP", "RETAIL", "CLAIMS"]
CORE_SERIES = {"CPI": "CPILFESL", "PCE": "PCEPILFE"}
HOURS_CAP = 168.0
FEATURE_NAMES = (
    ["z", "core_z", "abs_z", "z_missing"] + [f"kind_{k}" for k in PRIORITY]
    + ["atr15", "atr1h", "pre_range_atr15", "trend_score", "hours_since_prev", "overlap", "n_releases"])


@dataclass
class Dataset:
    t: np.ndarray  # int64 unix seconds, ascending
    X: np.ndarray  # float64, columns = feature_names
    y: np.ndarray  # int64 index into CLASSES (label60)
    y120: np.ndarray  # int64 index into CLASSES (label120), -1 if missing
    kind: np.ndarray  # primary kind per row
    absmove60: np.ndarray
    atr15: np.ndarray
    feature_names: list[str]
    move60: np.ndarray | None = None  # signed 60-minute move (price units); absmove60 is its absolute value
    none_row: np.ndarray | None = None  # bool per row: a stored feature was missing (n_none_features = its sum)
    n_none_features: int = 0  # rows where a stored feature (atr, range, trend, gap, overlap) was missing and became 0


def _num(v) -> float:
    return 0.0 if v is None else float(v)


def _core_z(kind: str, components: list[dict]) -> float | None:
    """Surprise z of the core series (CPI/PCE only), ignoring stale observations."""
    series = CORE_SERIES.get(kind)
    for c in components:
        if c.get("series") == series and not c.get("stale") and c.get("surprise_z") is not None:
            return float(c["surprise_z"])
    return None


def load(db: Path = store.DB) -> Dataset:
    """Read the database and build the dataset, sorted by release time."""
    with store.connect(db) as con:
        rows = con.execute(
            "SELECT r.t, r.atr15 AS r_atr15, r.move60, r.label60, r.label120, "
            "f.atr15 AS f_atr15, f.atr1h, f.pre_range, f.trend_score, f.hours_since_prev, f.overlap "
            "FROM reactions r LEFT JOIN features f ON f.t = r.t "
            "WHERE r.incomplete = 0 AND r.label60 IS NOT NULL ORDER BY r.t").fetchall()
        ev_rows = con.execute("SELECT kind, t, surprise_z, components FROM events").fetchall()
    by_t: dict[int, list] = {}
    for e in ev_rows:
        by_t.setdefault(e["t"], []).append(e)

    t, X, y, y120, kind, absmove, atr, move = [], [], [], [], [], [], [], []
    n_none = 0
    none_flags = []
    for r in rows:
        evs = by_t.get(r["t"])
        if not evs or any(e["kind"] not in PRIORITY for e in evs):
            evs = [e for e in (evs or []) if e["kind"] in PRIORITY]
        if not evs:
            continue  # reaction without a known event: cannot name a kind
        prim = min(evs, key=lambda e: PRIORITY.index(e["kind"]))
        z = prim["surprise_z"]
        core = _core_z(prim["kind"], json.loads(prim["components"] or "[]"))
        if any(r[c] is None for c in ("f_atr15", "atr1h", "pre_range", "trend_score", "hours_since_prev", "overlap")):
            n_none += 1
            none_flags.append(True)
        else:
            none_flags.append(False)
        atr15 = _num(r["f_atr15"])
        pre = _num(r["pre_range"])
        onehot = [1.0 if prim["kind"] == k else 0.0 for k in PRIORITY]
        X.append([_num(z), _num(core), abs(_num(z)), 1.0 if z is None else 0.0, *onehot,
                  atr15, _num(r["atr1h"]), pre / atr15 if atr15 > 0 else 0.0, _num(r["trend_score"]),
                  min(_num(r["hours_since_prev"]), HOURS_CAP), _num(r["overlap"]), float(len(evs))])
        t.append(r["t"])
        y.append(CLASSES.index(r["label60"]))
        y120.append(CLASSES.index(r["label120"]) if r["label120"] in CLASSES else -1)
        kind.append(prim["kind"])
        move.append(_num(r["move60"]))
        absmove.append(abs(_num(r["move60"])))
        atr.append(_num(r["r_atr15"]))
    return Dataset(np.array(t, dtype=np.int64), np.array(X, dtype=np.float64).reshape(len(t), len(FEATURE_NAMES)),
                   np.array(y, dtype=np.int64), np.array(y120, dtype=np.int64), np.array(kind, dtype=str),
                   np.array(absmove, dtype=np.float64), np.array(atr, dtype=np.float64), list(FEATURE_NAMES), np.array(move, dtype=np.float64),
                   np.array(none_flags, dtype=bool), n_none)
