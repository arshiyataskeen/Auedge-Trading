"""news_intel agent: advisory only, never votes, OK in every degraded case, JSON-safe extra."""
from __future__ import annotations

import asyncio
import json
import math
import os
import time
from datetime import datetime, timezone

import numpy as np
import pytest

from agents import news_intel as ni
from agents.base import run_agent
from agents.chief import chief
from core.models import AgentResult, MarketContext
from core.newsintel import live, mode as nmode
from core.newsintel.live import Intel
from test_live import CPI_EV, T, _walk, ctx_from_minutes, fake_art


def _ctx(now: float | None = None) -> MarketContext:
    now = time.time() if now is None else now
    return MarketContext(generated_at=datetime.fromtimestamp(now, timezone.utc), analysis_tf="15m")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("NEWSINTEL_MODE", raising=False)
    ni._cache.clear()
    yield
    ni._cache.clear()


def _run(agent, ctx):
    return asyncio.run(run_agent(agent, ctx))


def _with(monkeypatch, art=None, intel: Intel | None = None):
    monkeypatch.setattr(ni, "artifacts", lambda: art)
    if intel is not None:
        async def fake(ctx, now, a, timeout=8.0):
            return intel
        monkeypatch.setattr(ni, "build_intel_async", fake)


# ---------------------------------------------------------------- mode

@pytest.mark.parametrize("raw,want", [(None, "advisory"), ("off", "off"), ("LIVE", "live"), (" advisory ", "advisory"),
                                      ("bogus", "advisory")])
def test_mode(monkeypatch, raw, want):
    if raw is not None:
        monkeypatch.setenv("NEWSINTEL_MODE", raw)
    assert nmode.mode() == want


def test_effective_mode(monkeypatch):
    monkeypatch.setenv("NEWSINTEL_MODE", "live")
    assert nmode.effective_mode(fake_art(go_live=False)) == "advisory"
    assert nmode.effective_mode(None) == "advisory"
    assert nmode.effective_mode(fake_art(go_live=True)) == "live"
    monkeypatch.setenv("NEWSINTEL_MODE", "off")
    assert nmode.effective_mode(fake_art(go_live=True)) == "off"


# ---------------------------------------------------------------- the agent

def test_identity():
    a = ni.NewsIntelAgent()
    assert (a.name, a.label, a.weight, a.votes) == ("news_intel", "News intelligence", 0, False)


def test_off_mode(monkeypatch):
    monkeypatch.setenv("NEWSINTEL_MODE", "off")
    called = []
    monkeypatch.setattr(ni, "artifacts", lambda: called.append(1))
    r = _run(ni.NewsIntelAgent(), _ctx())
    assert r.status == "OK" and r.headline == "News intelligence is off" and r.extra == {} and not called
    assert (r.bias, r.confidence) == ("WAIT", 0)


def test_artifacts_missing(monkeypatch):
    _with(monkeypatch, art=None, intel=Intel(phase="none", notes=[live.NO_MODELS]))
    r = _run(ni.NewsIntelAgent(), _ctx())
    assert r.status == "OK" and (r.bias, r.confidence) == ("WAIT", 0)
    assert any("python -m core.newsintel.ml --export" in w for w in r.warnings)
    json.dumps(r.model_dump(mode="json"))


def test_live_requested_without_go_live(monkeypatch):
    monkeypatch.setenv("NEWSINTEL_MODE", "live")
    _with(monkeypatch, art=fake_art(go_live=False), intel=Intel(phase="none"))
    r = _run(ni.NewsIntelAgent(), _ctx())
    assert r.extra["mode"] == "advisory"
    assert any("advisory" in w.lower() and "live" in w.lower() for w in r.warnings)


def test_timeout_and_short_candles_are_ok(monkeypatch):
    """Real build_intel_async with no candles at all (market closed / feed gap) and with a timeout."""
    monkeypatch.setattr(ni, "artifacts", lambda: fake_art())
    monkeypatch.setattr(live.news, "events", lambda: [CPI_EV])
    r = _run(ni.NewsIntelAgent(), _ctx(T - 3600))
    assert r.status == "OK" and r.bias == "WAIT"
    assert r.extra["phase"] == "pre" and r.extra["expected_move"] is None
    monkeypatch.setattr(live, "build_intel", lambda *a, **k: time.sleep(0.3))
    monkeypatch.setattr(ni, "TIMEOUT_S", 0.05)
    r = _run(ni.NewsIntelAgent(), _ctx(T - 3600))
    assert r.status == "OK" and any("too long" in w for w in r.warnings)


def test_full_card_pre_and_post_json_safe(monkeypatch):
    m = _walk(1, T + 6 * 3600)
    art = fake_art()
    monkeypatch.setattr(ni, "artifacts", lambda: art)
    monkeypatch.setattr(live.news, "events", lambda: [CPI_EV])
    pre = _run(ni.NewsIntelAgent(), ctx_from_minutes(m, T - 3600))
    labels = [r[0] for r in pre.rows]
    for want in ("Next / last release", "Typical first-hour move", "Chances (advisory, not used for trades)",
                 "Surprise", "Similar past releases", "Model trust"):
        assert want in labels
    rows = dict(pre.rows)
    assert pre.bias_label == "BEFORE CPI"
    assert "actual not published yet" in rows["Surprise"]
    assert "$" in rows["Typical first-hour move"] and "forecast" not in json.dumps(pre.rows).lower()
    assert "up" in rows["Chances (advisory, not used for trades)"]
    assert "go-live: no" in rows["Model trust"]
    s = json.dumps(pre.model_dump())          # plain json, no default= helpers
    assert "NaN" not in s
    post = _run(ni.NewsIntelAgent(), ctx_from_minutes(m, T + 2700))
    assert post.bias_label == "AFTER CPI" and post.status == "OK"
    json.dumps(post.model_dump())
    inside = _run(ni.NewsIntelAgent(), ctx_from_minutes(m, T + 600))   # inside the 30-min no-trade window
    assert inside.bias_label == "AVOID" and inside.bias == "WAIT"


def test_uncertain_caveat_in_summary(monkeypatch):
    intel = Intel(phase="pre", event={"kind": "CPI", "name": "CPI", "t": T}, expected_move=5.0,
                  probs={"down": 0.33, "side": 0.34, "up": 0.33}, uncertain=True)
    _with(monkeypatch, art=fake_art(), intel=intel)
    r = _run(ni.NewsIntelAgent(), _ctx(T - 3600))
    assert "advisory" in r.summary.lower() and "not" in r.summary.lower()
    assert "uncertain: yes" in dict(r.rows)["Model trust"]


def test_avoid_label_when_gate_fired(monkeypatch):
    intel = Intel(phase="post", event={"kind": "NFP", "name": "NFP", "t": T}, m5_ratio=5.0)
    _with(monkeypatch, art=fake_art(m5_range_p99=2.5), intel=intel)
    r = _run(ni.NewsIntelAgent(), _ctx(T + 600))
    assert r.bias_label == "AVOID" and r.bias == "WAIT"


def test_no_news_label(monkeypatch):
    _with(monkeypatch, art=fake_art(), intel=Intel(phase="none"))
    r = _run(ni.NewsIntelAgent(), _ctx())
    assert r.bias_label == "NO NEWS"


def test_jsonable_numpy_and_nan():
    out = ni.jsonable({"a": np.float64(1.5), "b": float("nan"), "c": np.array([1.0, np.nan]), "d": (1, 2),
                       "e": np.int64(3), "f": {"g": np.bool_(True)}})
    assert out == {"a": 1.5, "b": None, "c": [1.0, None], "d": [1, 2], "e": 3, "f": {"g": True}}
    json.dumps(out, allow_nan=False)


# ---------------------------------------------------------------- artifact cache

def test_cache_reloads_on_meta_mtime(monkeypatch, tmp_path):
    loads = []
    monkeypatch.setattr(ni, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(ni, "load_artifacts", lambda p: loads.append(p) or "ART")
    assert ni.artifacts() is None and loads == []           # no meta.json: no load, no exception
    meta = tmp_path / "meta.json"
    meta.write_text("{}")
    assert ni.artifacts() == "ART" and ni.artifacts() == "ART" and len(loads) == 1
    os.utime(meta, (time.time() + 10, time.time() + 10))
    ni.artifacts()
    assert len(loads) == 2
    meta.unlink()
    assert ni.artifacts() is None


# ---------------------------------------------------------------- never influences the Chief

def test_chief_ignores_news_intel(monkeypatch):
    from agents import BUILT_IN
    import core.votes as votes
    m = _walk(2, T + 6 * 3600)
    ctx = ctx_from_minutes(m, T - 3600)
    others = [AgentResult(agent="trend", bias="BUY", confidence=70), AgentResult(agent="smc", bias="SELL", confidence=40)]
    news = AgentResult(agent="news_intel", bias="WAIT", confidence=0, extra={"phase": "pre"})
    agents = [a for a in BUILT_IN]
    base = {a.name: (a.weight if a.votes else 0) for a in agents} | {"trend": 1.0, "smc": 1.0}
    w = votes.weights(base)
    assert w.get("news_intel", 0) == 0
    for weights in (w, {"trend": 1.0, "smc": 1.0}):
        a = chief(ctx, others, weights, None).model_dump()
        b = chief(ctx, others + [news], weights, None).model_dump()
        a.pop("chips"), b.pop("chips")
        assert a == b
    # even a hostile BUY 100 from news_intel cannot move it: weight is 0 / missing
    loud = news.model_copy(update={"bias": "BUY", "confidence": 100})
    a = chief(ctx, others, w, None).model_dump()
    b = chief(ctx, others + [loud], w, None).model_dump()
    a.pop("chips"), b.pop("chips")
    assert a == b


def test_registered_before_skeptic_unless_off():
    from agents import BUILT_IN
    names = [a.name for a in BUILT_IN]
    if nmode.mode() != "off":
        assert names.index("news_intel") < names.index("skeptic")


def test_models_dir_matches_export():
    from core.newsintel.ml import export
    assert ni.MODELS_DIR == export.MODELS_DIR and ni.META == export.META

