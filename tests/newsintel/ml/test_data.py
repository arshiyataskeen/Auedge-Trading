"""Dataset loader: one row per release time, primary kind by priority, missing surprise kept with a flag."""
from __future__ import annotations

import numpy as np
import pytest

from core.newsintel import store
from core.newsintel.calendar import Component, Event
from core.newsintel.features import Features
from core.newsintel.ml import data
from core.newsintel.reactions import Reaction

DAY = 86400
T0 = 1_650_000_000


def comp(series, z, headline=True, stale=False):
    return Component(series, 1.0, 1.0, 1.0, 1.0, z, headline, stale)


def ev(kind, t, comps):
    return Event(kind, kind, t, comps)


def rea(t, label="up", l120="down", move=2.0, incomplete=0, atr=1.0):
    return Reaction(t, 1.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, atr, move, -move, label, l120, incomplete)


def fea(t, trend=0.3, hours=500.0, atr1h=2.0, pre=3.0, overlap=0):
    return Features(t, 1.0, atr1h, pre, trend, hours, overlap)


@pytest.fixture()
def db(tmp_path):
    ts = [T0 + i * DAY for i in range(6)]
    events = [
        ev("CLAIMS", ts[0], [comp("ICSA", 0.5)]),
        ev("CPI", ts[0], [comp("CPIAUCSL", 1.5), comp("CPILFESL", -0.7, headline=False)]),
        ev("FOMC", ts[1], []),
        ev("NFP", ts[2], [comp("PAYEMS", -2.0)]),
        ev("PCE", ts[3], [comp("PCEPI", 0.2), comp("PCEPILFE", 9.0, False, stale=True)]),
        ev("GDP", ts[4], [comp("GDP", 0.1)]),
        ev("PPI", ts[5], [comp("PPI", 0.1)]),  # incomplete reaction: dropped
    ]
    reactions = [rea(ts[0]), rea(ts[1], "side", None), rea(ts[2], "down"), rea(ts[3], "side"),
                 rea(ts[4], None), rea(ts[5], incomplete=1)]
    feats = [fea(ts[0]), fea(ts[1], hours=1.5), fea(ts[2], overlap=1), fea(ts[3]), fea(ts[4]), fea(ts[5])]
    path = tmp_path / "n.db"
    with store.connect(path) as con:
        store.replace_all(con, events, reactions, feats, "test")
    return path, ts


def test_rows_sorted_and_incomplete_dropped(db):
    path, ts = db
    ds = data.load(path)
    assert list(ds.t) == ts[:4]  # label-less GDP and incomplete PPI dropped
    assert ds.X.shape == (4, len(ds.feature_names))
    assert ds.X.dtype == np.float64 and ds.t.dtype == np.int64


def test_primary_kind_priority_and_n_releases(db):
    ds = data.load(db[0])
    assert list(ds.kind) == ["CPI", "FOMC", "NFP", "PCE"]
    f = {n: i for i, n in enumerate(ds.feature_names)}
    assert ds.X[0, f["n_releases"]] == 2 and ds.X[1, f["n_releases"]] == 1
    assert ds.X[0, f["kind_CPI"]] == 1 and ds.X[0, f["kind_CLAIMS"]] == 0


def test_missing_z_rows_kept_with_flag(db):
    ds = data.load(db[0])
    f = {n: i for i, n in enumerate(ds.feature_names)}
    assert ds.X[1, f["z"]] == 0 and ds.X[1, f["z_missing"]] == 1 and ds.X[1, f["abs_z"]] == 0
    assert ds.X[0, f["z"]] == 1.5 and ds.X[0, f["z_missing"]] == 0 and ds.X[0, f["abs_z"]] == 1.5
    assert ds.X[2, f["abs_z"]] == 2.0


def test_core_z_only_for_cpi_pce_and_not_stale(db):
    ds = data.load(db[0])
    f = {n: i for i, n in enumerate(ds.feature_names)}
    assert ds.X[0, f["core_z"]] == -0.7  # CPI core
    assert ds.X[3, f["core_z"]] == 0.0  # PCE core is stale
    assert ds.X[2, f["core_z"]] == 0.0


def test_feature_names_exact_order(db):
    ds = data.load(db[0])
    assert ds.feature_names == [
        "z", "core_z", "abs_z", "z_missing",
        "kind_FOMC", "kind_NFP", "kind_CPI", "kind_PCE", "kind_PPI", "kind_GDP", "kind_RETAIL", "kind_CLAIMS",
        "atr15", "atr1h", "pre_range_atr15", "trend_score", "hours_since_prev", "overlap", "n_releases"]


def test_labels_and_aux_columns(db):
    ds = data.load(db[0])
    assert data.CLASSES == ["down", "side", "up"]
    assert list(ds.y) == [2, 1, 0, 1]
    assert list(ds.y120) == [0, -1, 0, 0]
    assert list(ds.absmove60) == [2.0] * 4
    f = {n: i for i, n in enumerate(ds.feature_names)}
    assert ds.X[0, f["hours_since_prev"]] == 168  # capped
    assert ds.X[1, f["hours_since_prev"]] == 1.5
    assert ds.X[0, f["pre_range_atr15"]] == 3.0
    assert ds.X[2, f["overlap"]] == 1
