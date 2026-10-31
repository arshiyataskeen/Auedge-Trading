import sqlite3

import numpy as np

from core.newsintel import build
from core.newsintel.calendar import Component, Event
from core.newsintel.minutes import Minutes

T0 = 1_700_000_000 - 1_700_000_000 % 60


def _minutes(n=3 * 1440):
    t = T0 + 60 * np.arange(n, dtype=np.int64)
    rng = np.random.default_rng(1)
    c = 2000.0 + np.cumsum(rng.normal(0, 0.4, n))
    o = np.concatenate([[c[0]], c[:-1]])
    return Minutes(t, o, np.maximum(o, c) + 0.2, np.minimum(o, c) - 0.2, c)


def _event(kind, t, z=1.0):
    comps = [Component("X", 1.0, 0.5, 0.8, 0.2, z, True)] if kind != "FOMC" else []
    return Event(kind, kind + " name", t, comps)


def _run(monkeypatch, tmp_path, events, argv_extra=()):
    monkeypatch.setattr(build, "load_backup_minutes", lambda backup: _minutes())
    monkeypatch.setattr(build, "build_events", lambda since="2020-01-01", offline=False: events)
    db = tmp_path / "n.db"
    out = build.main(["--backup", "x.backup", "--db", str(db), *argv_extra])
    return out, db


def _rows(db, table):
    con = sqlite3.connect(db)
    try:
        return con.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
    finally:
        con.close()


def test_shared_release_time_one_reaction(monkeypatch, tmp_path):
    t1, t2 = T0 + 1440 * 60, T0 + 2 * 1440 * 60
    evs = [_event("CPI", t1), _event("PPI", t1), _event("FOMC", t2)]
    out, db = _run(monkeypatch, tmp_path, evs)
    assert len(_rows(db, "reactions")) == 2
    assert len(_rows(db, "features")) == 2
    assert len(_rows(db, "events")) == 3
    assert out["events"] == 3 and out["times"] == 2
    assert out["by_kind"] == {"CPI": 1, "PPI": 1, "FOMC": 1}


def test_build_idempotent(monkeypatch, tmp_path):
    evs = [_event("CPI", T0 + 1440 * 60), _event("FOMC", T0 + 2 * 1440 * 60)]
    out1, db = _run(monkeypatch, tmp_path, evs)
    r1, e1 = _rows(db, "reactions"), _rows(db, "events")
    out2, _ = _run(monkeypatch, tmp_path, evs)
    assert out1 == out2
    assert _rows(db, "reactions") == r1
    assert _rows(db, "events") == e1


def test_events_outside_data_range_skipped(monkeypatch, tmp_path):
    m = _minutes()
    evs = [_event("CPI", int(m.t[0]) - 3600), _event("PPI", T0 + 1440 * 60),
           _event("NFP", int(m.t[-1]) + 3600)]
    out, db = _run(monkeypatch, tmp_path, evs)
    assert out["events"] == 1 and out["times"] == 1
    assert [r[1] for r in _rows(db, "events")] == ["PPI"]
