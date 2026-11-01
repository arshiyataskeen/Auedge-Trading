"""Final-review fixes: backtest model override + in-sample flag, async artifacts, chief hook isolation, pruning."""
from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


def _art(through):
    return SimpleNamespace(trained_through=through, m5_range_p99=1.0, go_live=False)


def test_backtest_models_env_used_and_flag(monkeypatch, tmp_path):
    import backtest as bt
    seen = []
    monkeypatch.setenv("NEWSINTEL_BT_MODELS", str(tmp_path))
    monkeypatch.setattr(bt, "_load_models", lambda p: (seen.append(str(p)), _art("2026-03-01"))[1])
    monkeypatch.setattr(bt._news_intel, "artifacts", lambda: pytest.fail("live export must not be used"))
    assert bt._bt_artifacts().trained_through == "2026-03-01"
    assert seen == [str(tmp_path)]
    ts = lambda d: int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp())
    assert bt.news_models_info(ts("2026-02-01")) == {"news_models_trained_through": "2026-03-01", "news_in_sample": True}
    assert bt.news_models_info(ts("2026-03-01"))["news_in_sample"] is True
    assert bt.news_models_info(ts("2026-03-02"))["news_in_sample"] is False


def test_backtest_models_default_is_live_export(monkeypatch):
    import backtest as bt
    monkeypatch.delenv("NEWSINTEL_BT_MODELS", raising=False)
    monkeypatch.setattr(bt._news_intel, "artifacts", lambda: _art("2026-08-14"))
    info = bt.news_models_info(int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp()))
    assert info == {"news_models_trained_through": "2026-08-14", "news_in_sample": False}
    monkeypatch.setattr(bt._news_intel, "artifacts", lambda: None)
    assert bt.news_models_info(0) == {"news_models_trained_through": None, "news_in_sample": False}


def test_psychology_loads_artifacts_off_the_loop(monkeypatch):
    import agents.news_intel as ni
    from core.newsintel import gates
    import agents.psychology as psy
    src = open(psy.__file__, encoding="utf-8").read()
    assert "to_thread" in src
    # the loader must run in a worker thread when analyze runs on the loop
    names = []
    monkeypatch.setattr(ni, "artifacts", lambda: names.append(threading.current_thread().name) or None)

    async def go():
        await psy._load_artifacts_async()
    asyncio.run(go())
    assert names and names[0] != threading.main_thread().name


def test_artifacts_cache_reload_is_locked(monkeypatch, tmp_path):
    import agents.news_intel as ni
    (tmp_path / ni.META).write_text("{}")
    monkeypatch.setattr(ni, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(ni, "_cache", {})
    calls = []

    def slow(p):
        calls.append(1)
        time.sleep(0.2)
        return "ART"
    monkeypatch.setattr(ni, "load_artifacts", slow)
    out = []
    ts = [threading.Thread(target=lambda: out.append(ni.artifacts())) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert out == ["ART"] * 4 and len(calls) == 1


def test_app_chief_hook_failure_leaves_report(monkeypatch):
    import app
    assert hasattr(app, "_apply_news_hook")
    import core.newsintel.chief_hook as ch
    monkeypatch.setattr(ch, "apply_from_results", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    rep = SimpleNamespace(x=1)
    app._apply_news_hook(rep, [])
    assert rep.x == 1


def test_inflight_pruned():
    from core.newsintel import live

    async def go():
        done = asyncio.get_running_loop().create_future()
        d = asyncio.create_task(asyncio.sleep(0))
        await d
        live._inflight.clear()
        live._inflight[("OLD", 1)] = d
        live._prune_inflight()
        assert live._inflight == {}
    asyncio.run(go())


def test_chief_hook_uses_chief_word():
    from agents import chief
    from core.newsintel import chief_hook
    for c in (0, 49, 50, 69, 70, 85):
        assert chief_hook._word(c) == chief.confidence_word(c)
