"""Chief hook: off = identical, advisory = one reason line, live = bounded adjustments, never a new trade."""
from __future__ import annotations

import pytest

from agents.chief import MAX_CONFIDENCE, ChiefReport, TradePlan
from core.models import AgentResult
from core.newsintel.chief_hook import apply_news


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("NEWSINTEL_MODE", raising=False)


def _rep(bias="BUY", conf=60, kind="now"):
    plan = TradePlan(kind=kind, action=bias, side=bias, entry_lo=1.0, stop=0.5) if kind != "none" else TradePlan()
    return ChiefReport(bias=bias, confidence=conf, plan=plan, reasons=["a"])


def _news(mode="advisory", up=0.5, down=0.2, uncertain=False):
    ex = {"mode": mode, "phase": "pre", "event": {"kind": "CPI", "name": "CPI", "t": 1}, "expected_move": 12.5,
          "expected_range": [8.0, 20.0], "probs": {"up": up, "side": 1 - up - down, "down": down},
          "similar": [{"label": "up"}, {"label": "down"}, {"label": "up"}], "uncertain": uncertain}
    return AgentResult(agent="news_intel", extra=ex)


def test_off_identical(monkeypatch):
    monkeypatch.setenv("NEWSINTEL_MODE", "off")
    r = _rep()
    before = r.model_dump()
    apply_news(r, _news("live"))
    assert r.model_dump() == before


def test_advisory_only_adds_reason():
    r = _rep()
    before = r.model_dump()
    apply_news(r, _news("advisory", up=0.1, down=0.8))
    after = r.model_dump()
    assert len(after["reasons"]) == 2 and "typical first-hour move about $12.50 (range 8.00–20.00)" in after["reasons"][1] and "expect" not in after["reasons"][1] and after["reasons"][1].startswith("News (advisory)") and "similar past releases" in after["reasons"][1]
    after["reasons"] = before["reasons"]
    assert after == before


def test_none_news_is_noop():
    r = _rep()
    before = r.model_dump()
    apply_news(r, None)
    assert r.model_dump() == before


def test_live_weak_side_turns_wait():
    r = _rep("BUY")
    apply_news(r, _news("live", up=0.2, down=0.5))
    assert r.bias == "WAIT" and r.plan.kind == "none" and r.plan.action == "WAIT (news view disagrees)"
    assert r.confidence == 40 and r.confidence_word == "Low"
    r = _rep("BUY", conf=30)
    apply_news(r, _news("live", up=0.2, down=0.5))
    assert r.confidence == 30


def test_live_prefix():
    r = _rep()
    apply_news(r, _news("live", up=0.5, down=0.2))
    assert r.reasons[1].startswith("News (live):")


def test_live_missing_probs_only_reason():
    r = _rep()
    before = r.model_dump()
    n = _news("live")
    n.extra["probs"] = None
    apply_news(r, n)
    after = r.model_dump()
    assert len(after["reasons"]) == 2
    after["reasons"] = before["reasons"]
    assert after == before


def test_live_boost_and_uncertain_together():
    r = _rep("BUY", conf=60)
    apply_news(r, _news("live", up=0.7, down=0.1, uncertain=True))
    assert r.confidence == 55


def test_apply_from_results_swallows(monkeypatch, capsys):
    import core.newsintel.chief_hook as h
    monkeypatch.setattr(h, "apply_news", lambda *a: 1 / 0)
    r = _rep()
    h.apply_from_results(r, [_news()])
    assert r.confidence == 60 and "chief hook skipped" in capsys.readouterr().err


def test_live_cap():
    r = _rep("BUY", conf=MAX_CONFIDENCE - 2)
    apply_news(r, _news("live", up=0.7, down=0.1))
    assert r.confidence == MAX_CONFIDENCE
    r = _rep("SELL", conf=60)
    apply_news(r, _news("live", up=0.1, down=0.6, uncertain=True))
    assert r.confidence == 55


def test_live_never_creates_trade():
    r = _rep("WAIT", conf=40, kind="none")
    apply_news(r, _news("live", up=0.9, down=0.0))
    assert r.plan.kind == "none" and r.bias == "WAIT" and r.confidence == 40


def test_early_return_fills_quality():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from test_live import T, _walk, ctx_from_minutes
    from agents.chief import chief
    ctx = ctx_from_minutes(_walk(2, T + 6 * 3600), T - 3600)
    r = chief(ctx, [], {}, None)           # data check missing -> early return
    assert r.bias == "WAIT" and r.headline.startswith("NO TRADE") and r.quality and "score" in r.quality
