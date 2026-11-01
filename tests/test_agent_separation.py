"""Signal separation: does gold behave differently after an agent's calls? Read-only analysis."""
import json
import sqlite3

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import agent_separation as sep

DAY = 86400


def make_rows(n=1500, seed=1):
    rng = np.random.default_rng(seed)
    now = 1_800_000_000
    rows = []
    for i in range(n):
        t = now - (n - i) * 3600 * 4
        move = float(rng.normal(0, 10))
        truth = "BUY" if move > 0 else "SELL"
        flip = "SELL" if truth == "BUY" else "BUY"
        good = truth if rng.random() < 0.7 else flip       # informed: right 70% of the time it speaks
        votes = {
            "good": good if rng.random() < 0.6 else "WAIT",
            "rand": ("BUY" if rng.random() < .5 else "SELL") if rng.random() < 0.6 else "WAIT",
            "bad": (flip if good == truth else truth) if rng.random() < 0.6 else "WAIT",
            "tiny": "BUY" if i < 10 else "WAIT",
        }
        rows.append((t, move, votes))
    return rows


@pytest.fixture(scope="module")
def result():
    return {r["agent"]: r for r in sep.separation(make_rows(), draws=200)}


def test_informative_agent_is_useful(result):
    r = result["good"]
    assert r["verdict"] == "useful" and r["mean"] > 0 and r["lo"] > 0 and r["n"] >= 30


def test_random_agent_has_no_clear_signal(result):
    assert result["rand"]["verdict"] == "none"


def test_inverted_agent_is_harmful(result):
    r = result["bad"]
    assert r["verdict"] == "harmful" and r["mean"] < 0


def test_tiny_n_is_too_few(result):
    assert result["tiny"]["verdict"] == "too_few" and result["tiny"]["n"] == 10


def test_one_sided_agent_still_scored():
    rows = [(1_800_000_000 - i * 3600, float(np.sin(i)) * 5, {"a": "SELL"}) for i in range(100)]
    assert sep.separation(rows, draws=50)[0]["n"] == 100


def test_result_shape_and_determinism(result):
    r = result["good"]
    assert set(r) == {"agent", "n", "mean", "hit_rate", "distance", "lo", "hi", "verdict", "drift", "source"}
    assert 0 <= r["hit_rate"] <= 100 and r["lo"] <= r["distance"] <= r["hi"]
    again = {x["agent"]: x for x in sep.separation(make_rows(), draws=200)}
    assert again["good"]["distance"] == r["distance"] and again["good"]["lo"] == r["lo"]


def test_drift_flags_a_recently_flipped_agent():
    rng = np.random.default_rng(3)
    now = 1_800_000_000
    rows = []
    for i in range(1600):
        t = now - i * 3600 * 2
        move = float(rng.normal(0, 10))
        right = "BUY" if move > 0 else "SELL"
        wrong = "SELL" if move > 0 else "BUY"
        recent = t > now - 30 * DAY
        rows.append((t, move, {"flip": right if recent or rng.random() < .5 else wrong}))
    r = sep.separation(rows, draws=200, now=now)[0]
    assert r["drift"] and r["drift"]["flag"] is True
    assert r["drift"]["recent_distance"] > r["drift"]["prior_distance"]


def test_drift_none_when_recent_too_small():
    rows = make_rows()
    for r in sep.separation(rows, draws=50, now=rows[-1][0] + 400 * DAY):
        assert r["drift"] is None


def test_never_mutates_input():
    rows = make_rows(200)
    snap = repr(rows)
    sep.separation(rows, draws=20)
    assert repr(rows) == snap


def test_api_shape(monkeypatch):
    from core import separation_api
    monkeypatch.setattr(separation_api, "load_rows", lambda: (make_rows(400), "unit"))
    separation_api._cache.clear()
    app = FastAPI()
    app.include_router(separation_api.router)
    r = TestClient(app).get("/api/agents/separation")
    assert r.status_code == 200
    body = r.json()
    assert {x["agent"] for x in body} == {"good", "rand", "bad", "tiny"}
    assert all(x["source"] == "unit" and "verdict" in x for x in body)
    separation_api._cache.clear()


def test_load_rows_reads_dataset_db(tmp_path):
    db = tmp_path / "d.db"
    c = sqlite3.connect(db)
    c.execute("create table steps (src text, t integer, fwd_4h real, agents text)")
    c.executemany("insert into steps values (?,?,?,?)", [
        ("live", 1000, 3.0, json.dumps({"smc": {"bias": "SELL"}})),
        ("backtest_1h", 1100, 2.0, json.dumps({"smc": {"bias": "BUY"}})),     # same hour: deduped
        ("backtest_1h", 8000, None, json.dumps({"smc": {"bias": "BUY"}})),    # unscored: skipped
        ("backtest_1h", 20000, -1.0, json.dumps({"smc": {"bias": "BUY"}}))])
    c.commit()
    c.close()
    rows, source = sep.load_rows(db)
    assert [(r[0], r[1], r[2]["smc"]) for r in rows] == [(1000, 3.0, "SELL"), (20000, -1.0, "BUY")]
    assert "live" in source and "backtest" in source
