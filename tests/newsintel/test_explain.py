"""Claude note: one call per note_key, never awaited by the agent, no key/none phase -> no call, errors -> no note."""
from __future__ import annotations

import asyncio
import json
import sys
import time
import types

import pytest

from agents import news_intel as ni
from agents.base import run_agent
from core import ai_summary
from core.newsintel import explain
from core.newsintel.live import Intel
from test_agent import _ctx, _with


def intel(phase="post", z=1.234, t=1_700_000_000):
    return Intel(phase=phase, event={"kind": "CPI", "name": "US CPI", "t": t} if phase != "none" else None,
                 surprise_z=z if phase == "post" else None, expected_move=12.5,
                 probs={"down": 0.3, "side": 0.3, "up": 0.4},
                 similar=[{"date": "2024-05-15", "kind": "CPI", "move": 9.0}],
                 features={"secret_feature": 1.0}, notes=["internal note"], go_live=True)


class FakeClient:
    calls: list = []
    fail = False

    def __init__(self, *a, **k):
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=self.create))

    async def create(self, **kw):
        FakeClient.calls.append(kw)
        if FakeClient.fail:
            raise FakeClient.APIError("boom")
        return types.SimpleNamespace(stop_reason="end_turn",
                                     content=[types.SimpleNamespace(type="text", text="  Plain note.  ")])


class _APIError(Exception):
    pass


FakeClient.APIError = _APIError


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    FakeClient.calls, FakeClient.fail = [], False
    mod = types.SimpleNamespace(AsyncAnthropic=FakeClient, APIError=_APIError)
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setattr(ai_summary, "enabled", lambda: True)
    monkeypatch.setattr(explain, "NOTES_PATH", tmp_path / "notes.json")
    explain._cache.clear()
    ni._asked.clear()
    yield
    explain._cache.clear()
    ni._asked.clear()


def test_note_key():
    assert explain.note_key(intel("none")) is None
    assert explain.note_key(intel()) == "1700000000|post|1.2"
    assert explain.note_key(intel("pre")) == "1700000000|pre|"


def test_refresh_writes_cache_and_disk_and_prompt_only_intel_fields():
    i = intel()
    asyncio.run(explain.refresh_note(i))
    assert explain.cached_note(i) == "Plain note."
    prompt = FakeClient.calls[0]["messages"][0]["content"]
    sent = json.loads(prompt)
    allowed = set(Intel.__dataclass_fields__) | {"chances_label"}
    assert set(sent) <= allowed
    assert "secret_feature" not in prompt and "internal note" not in prompt
    assert "70 words" in FakeClient.calls[0]["system"]
    explain._cache.clear()
    assert explain.cached_note(i) == "Plain note."          # read back from notes.json
    assert json.loads(explain.NOTES_PATH.read_text())[explain.note_key(i)] == "Plain note."


def test_no_call_when_disabled_or_no_phase(monkeypatch):
    asyncio.run(explain.refresh_note(intel("none")))
    monkeypatch.setattr(ai_summary, "enabled", lambda: False)
    asyncio.run(explain.refresh_note(intel()))
    assert FakeClient.calls == [] and explain.cached_note(intel()) is None


def test_api_error_gives_no_note():
    FakeClient.fail = True
    asyncio.run(explain.refresh_note(intel()))
    assert explain.cached_note(intel()) is None


def test_agent_one_call_per_key_and_never_awaits(monkeypatch):
    _with(monkeypatch, intel=intel())

    async def go():
        a = ni.NewsIntelAgent()
        rs = [await run_agent(a, _ctx()) for _ in range(3)]
        await asyncio.gather(*list(ni._tasks))
        return rs

    rs = asyncio.run(go())
    assert len(FakeClient.calls) == 1
    assert not any(r[0].startswith("Plain-language note") for r in rs[0].rows)   # first run: no note yet
    r4 = asyncio.run(run_agent(ni.NewsIntelAgent(), _ctx()))
    assert any(r[0].startswith("Plain-language note") and r[1] == "Plain note." for r in r4.rows)
    assert r4.summary == "Plain note."
    assert len(FakeClient.calls) == 1


def test_agent_no_request_offline_or_old_context(monkeypatch):
    _with(monkeypatch, intel=intel())

    async def go(ctx):
        await run_agent(ni.NewsIntelAgent(), ctx)
        await asyncio.gather(*list(ni._tasks))

    with ni.offline():
        asyncio.run(go(_ctx()))
    asyncio.run(go(_ctx(time.time() - 3600)))
    assert FakeClient.calls == []


def test_agent_survives_refresh_error(monkeypatch):
    _with(monkeypatch, intel=intel())
    FakeClient.fail = True

    async def go():
        r = await run_agent(ni.NewsIntelAgent(), _ctx())
        await asyncio.gather(*list(ni._tasks))
        return r

    assert asyncio.run(go()).status == "OK"
