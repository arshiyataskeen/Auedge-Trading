"""Task 10: the review board's rule for INTEL_* filters, undo, and the manual toggle."""
import pytest

import backtest as bt
from core import votes
from core.intel import flags


def _v(h1, h2, m=None, dd=1.0):
    return {"h1_rpt": h1, "h2_rpt": h2, "rpt": m, "dd_r": dd}


def test_rule_needs_both_halves_month_and_dd():
    base, bm = _v(0.1, 0.1, dd=2.0), _v(None, None, 0.1)
    assert bt.intel_better(_v(0.2, 0.2, dd=2.0), base, _v(0, 0, 0.1), bm)
    assert not bt.intel_better(_v(0.2, 0.05, dd=2.0), base, _v(0, 0, 0.2), bm)      # one half only
    assert not bt.intel_better(_v(0.2, 0.2, dd=2.0), base, _v(0, 0, 0.05), bm)      # last month disagrees
    assert not bt.intel_better(_v(0.2, 0.2, dd=3.0), base, _v(0, 0, 0.2), bm)       # deeper drawdown
    assert not bt.intel_better(_v(None, 0.2), base, _v(0, 0, 0.2), bm)              # no trades: no change


def test_parse_intel():
    assert bt.parse_intel("align,vol") == {"ALIGN": True, "VOL": True}
    assert bt.parse_intel("all") == {f: True for f in bt.INTEL_FLAGS}
    assert bt.parse_intel(None) is None
    with pytest.raises(ValueError):
        bt.parse_intel("nope")


def test_intel_env_restores(monkeypatch):
    monkeypatch.delenv("INTEL_VOL", raising=False)
    with bt.intel_env({"VOL": True}):
        assert flags.flag("VOL")
    import os
    assert "INTEL_VOL" not in os.environ


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(flags, "PATH", tmp_path / "intel_flags.json")
    monkeypatch.setattr(votes, "VOTES", tmp_path / "votes.json")
    monkeypatch.setattr(votes, "LOG", tmp_path / "log.json")
    monkeypatch.setattr(votes, "DATA", tmp_path)
    for f in bt.INTEL_FLAGS:
        monkeypatch.delenv("INTEL_" + f, raising=False)
    return tmp_path


def test_change_logs_and_undo_restores_filters(tmp_state):
    votes.change([], "review board", [{"flag": "VOL", "action": "on"}], "6m better", "rv_1", intel_after={"VOL": True})
    assert flags.flag("VOL")
    e = votes.log()[-1]
    assert e["intel_before"] == {"VOL": False} and e["intel_after"] == {"VOL": True}
    votes.undo()
    assert not flags.flag("VOL")
    assert votes.log()[-1]["by"] == "undo"


def test_manual_toggle_endpoint(tmp_state):
    from fastapi.testclient import TestClient
    import app as appmod
    c = TestClient(appmod.app)
    r = c.post("/api/intel/flags", json={"name": "ENTRY", "on": True}).json()
    assert r["ok"] and any(f["name"] == "ENTRY" and f["on"] and f["by"] == "you" for f in r["flags"])
    assert c.post("/api/intel/flags", json={"name": "BAD", "on": True}).json()["ok"] is False
    assert votes.log()[-1]["by"] == "you"
    assert any(f["name"] == "ENTRY" for f in c.get("/api/review").json()["filters"])
