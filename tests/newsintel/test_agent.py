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
        async def fake(ctx, now, a, timeout=8.0, background=False):
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
    assert (a.name, a.label, a.weight, a.votes) == ("news_intel", "News intelligence", 1.0, True)


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
    assert r.extra["m5"] == {"bos": None, "retest": None, "text": "Not enough 5-minute candles"}
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

def test_chief_ignores_news_intel(monkeypatch, tmp_path):
    import core.votes as _v
    monkeypatch.setattr(_v, "VOTES", tmp_path / "v.json")   # default state, never the real file
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


@pytest.mark.parametrize("m", ["advisory", "live", "off"])
def test_registry_for_mode(m):
    from agents import built_in
    names = [a.name for a in built_in(m)]
    if m == "off":
        assert "news_intel" not in names
    else:
        assert names.index("news_intel") < names.index("skeptic")


def test_models_dir_matches_export():
    from core.newsintel.ml import export
    assert ni.MODELS_DIR == export.MODELS_DIR and ni.META == export.META



# ---------------------------------------------------------------- fix round 1

def _no_cache(monkeypatch):
    monkeypatch.setattr(live, "_found", {})
    monkeypatch.setattr(live, "_tried", {})
    monkeypatch.setattr(live, "_inflight", {})
    monkeypatch.setattr(live, "_cached_rows", lambda sid: (_ for _ in ()).throw(RuntimeError("no cache")))


def _downloads(monkeypatch):
    calls = []
    monkeypatch.setattr(live.fred, "download", lambda sid: calls.append(sid) or [])
    return calls


def _run_and_drain(agent, ctx):
    async def go():
        r = await run_agent(agent, ctx)
        await asyncio.gather(*live._inflight.values(), return_exceptions=True)
        return r
    return asyncio.run(go())


def test_historical_context_never_downloads(monkeypatch):
    """A backtest step just after a past release with no cached surprise: no FRED call, surprise unknown."""
    _no_cache(monkeypatch)
    calls = _downloads(monkeypatch)
    monkeypatch.setattr(ni, "artifacts", lambda: fake_art())
    monkeypatch.setattr(live.news, "events", lambda: [CPI_EV])
    m = _walk(1, T + 6 * 3600)
    r = _run_and_drain(ni.NewsIntelAgent(), ctx_from_minutes(m, T + 2700))
    assert r.status == "OK" and r.extra["phase"] == "post" and r.extra["surprise_z"] is None
    assert calls == [] and live._inflight == {}


def _current_post_cpi(monkeypatch):
    _no_cache(monkeypatch)
    calls = _downloads(monkeypatch)
    now = time.time()
    ev = {"t": int(now) - 1200, "name": "CPI (inflation)", "kind": "CPI"}
    monkeypatch.setattr(ni, "artifacts", lambda: fake_art())
    monkeypatch.setattr(live.news, "events", lambda: [ev])
    return calls, now


def test_offline_scope_blocks_download_even_for_a_current_context(monkeypatch):
    calls, now = _current_post_cpi(monkeypatch)

    async def go():
        with ni.offline():
            await run_agent(ni.NewsIntelAgent(), _ctx(now))
        await asyncio.gather(*live._inflight.values(), return_exceptions=True)
    asyncio.run(go())
    assert calls == []
    _run_and_drain(ni.NewsIntelAgent(), _ctx(now))           # outside the scope: the live app's one lookup
    assert calls == ["CPIAUCSL"]


def test_importing_backtest_keeps_live_fetch(monkeypatch):
    from backtest import load_data  # noqa: F401 - exactly what app.py does at startup
    calls, now = _current_post_cpi(monkeypatch)
    _run_and_drain(ni.NewsIntelAgent(), _ctx(now))
    assert calls == ["CPIAUCSL"]


def test_backtest_analyse_is_offline(monkeypatch):
    import backtest as bt
    calls, now = _current_post_cpi(monkeypatch)
    monkeypatch.setattr(bt, "BUILT_IN", [ni.NewsIntelAgent()])
    seen = []
    real = ni.build_intel_async

    async def spy(*a, **k):
        seen.append(k.get("background"))
        return await real(*a, **k)
    monkeypatch.setattr(ni, "build_intel_async", spy)

    async def go():
        try:
            await bt.analyse(_ctx(now))
        except Exception:  # noqa: BLE001 - the Chief on an empty context is not under test here
            pass
        await asyncio.gather(*live._inflight.values(), return_exceptions=True)
    asyncio.run(go())
    assert seen == [False] and calls == []

def test_import_failure_gives_ok_card(monkeypatch):
    def broken():
        raise ImportError("no module named sklearn")
    monkeypatch.setattr(ni, "_live", broken)
    r = _run(ni.NewsIntelAgent(), _ctx())
    assert r.status == "OK" and (r.bias, r.confidence) == ("WAIT", 0)
    assert r.headline.startswith("News intelligence unavailable") and "sklearn" in r.headline

def test_skeptic_ignores_non_voting_prior():
    from agents.skeptic import SkepticAgent
    ctx = ctx_from_minutes(_walk(3, T + 6 * 3600, days=200), T)
    news = AgentResult(agent="news_intel")
    ctx.prior = [AgentResult(agent="trend", status="ERROR"), news]
    assert asyncio.run(SkepticAgent().analyze(ctx)).status == "INSUFFICIENT_DATA"
    ctx.prior = [AgentResult(agent="trend", bias="BUY", confidence=60), news]
    assert asyncio.run(SkepticAgent().analyze(ctx)).status == "OK"


def test_m5_uses_only_candles_finished_before_generated_at(monkeypatch):
    from core.models import Candle, CandleSet
    from core.newsintel import m5 as m5mod
    seen = {}
    monkeypatch.setattr(m5mod, "m5_confirmations", lambda cs: seen.setdefault("t", [c.t for c in cs]) and
                        {"bos": None, "retest": None, "text": "x"})
    monkeypatch.setattr(ni, "artifacts", lambda: fake_art())
    monkeypatch.setattr(live.news, "events", lambda: [])
    now = 1_700_000_000
    cut = now - now % 300
    cs = [Candle(t=cut - 300 * k, o=1, h=2, l=0, c=1) for k in range(6, 0, -1)]   # last one ends exactly at cut
    cs += [Candle(t=cut, o=1, h=2, l=0, c=1), Candle(t=cut + 300, o=1, h=2, l=0, c=1)]  # forming + future
    ctx = _ctx(cut)
    ctx.candles["fut_5m"] = CandleSet(key="fut_5m", timeframe="5m", kind="futures", source_label="t",
                                      candles=cs, last_is_forming=True)
    _run(ni.NewsIntelAgent(), ctx)
    assert seen["t"] == [c.t for c in cs[:6]]
    # candle at generated_at is dropped even when not flagged forming
    seen.clear()
    ctx.candles["fut_5m"].last_is_forming = False
    ctx.candles["fut_5m"].candles = cs[:7]
    _run(ni.NewsIntelAgent(), ctx)
    assert seen["t"] == [c.t for c in cs[:6]]
