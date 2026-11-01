"""The news vote: rule, default-off, chief promotion, review board handling."""
import pytest

from core import votes
from core.models import AgentResult
from core.newsintel.live import Intel
from core.newsintel.mode import NEWS_AGENT
from core.newsintel.vote import news_vote, promote

EV = {"kind": "CPI", "name": "CPI", "t": 1}


def _i(phase="pre", up=0.5, down=0.2, uncertain=False, event=EV):
    return Intel(phase=phase, event=event, probs={"up": up, "down": down, "side": 1 - up - down}, uncertain=uncertain)


@pytest.mark.parametrize("kw,want", [
    ({}, ("BUY", 50)), ({"up": 0.2, "down": 0.6}, ("SELL", 60)), ({"up": 0.44, "down": 0.3}, ("WAIT", 0)),
    ({"up": 0.45, "down": 0.1}, ("BUY", 45)), ({"uncertain": True}, ("WAIT", 0)), ({"phase": "none"}, ("WAIT", 0)),
    ({"event": None}, ("WAIT", 0)), ({"phase": "post"}, ("BUY", 50))])
def test_rule(kw, want):
    v = news_vote(_i(**kw))
    assert (v["bias"], v["confidence"]) == want


def test_no_probs():
    assert news_vote(Intel(phase="pre", event=EV))["bias"] == "WAIT"


def test_promote_only_with_weight():
    r = AgentResult(agent=NEWS_AGENT, extra={"vote": {"bias": "BUY", "confidence": 55}})
    assert promote([r], {NEWS_AGENT: 0})[0].bias == "WAIT"
    assert promote([r], {})[0].bias == "WAIT"
    p = promote([r], {NEWS_AGENT: 1.0})[0]
    assert (p.bias, p.confidence) == ("BUY", 55)


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(votes, "VOTES", tmp_path / "v.json")
    monkeypatch.setattr(votes, "LOG", tmp_path / "l.json")
    monkeypatch.setattr(votes, "DATA", tmp_path)


def test_default_off_and_roundtrip(tmp_state):
    assert NEWS_AGENT in votes.off()
    assert votes.weights({NEWS_AGENT: 1.0, "a": 1.0})[NEWS_AGENT] == 0
    votes.change(["stophunt"], "review board", [{"agent": NEWS_AGENT, "action": "on"}])   # news not in new_off = on
    assert NEWS_AGENT not in votes.off() and votes.weights({NEWS_AGENT: 1.0})[NEWS_AGENT] == 1.0
    votes.set_auto_apply(False)
    assert NEWS_AGENT not in votes.off()
    votes.undo()
    assert NEWS_AGENT in votes.off() and votes.off().count("stophunt") == 0
    votes.change(sorted(set(votes.off()) | {"x"}), "you", [])          # other change keeps news off
    assert NEWS_AGENT in votes.off()


def test_agent_carries_candidate_vote_but_says_wait(monkeypatch):
    from agents import news_intel as ni
    from tests.newsintel import test_agent as ta
    intel = Intel(phase="pre", event={"kind": "CPI", "name": "CPI", "t": 1.0e9 + 3600},
                  probs={"up": 0.6, "down": 0.2, "side": 0.2})
    ta._with(monkeypatch, art=ta.fake_art(), intel=intel)
    r = ta._run(ni.NewsIntelAgent(), ta._ctx(1.0e9))
    assert (r.bias, r.confidence) == ("WAIT", 0) and r.extra["vote"] == {"bias": "BUY", "confidence": 60}
    assert promote([r], {NEWS_AGENT: 1.0})[0].bias == "BUY"


def test_review_flags_in_sample(monkeypatch):
    import backtest as bt
    monkeypatch.setattr(bt, "_bt_artifacts", lambda: type("A", (), {"trained_through": "2026-10-15"})())
    assert bt.news_models_info(1790000000)["news_in_sample"] is True      # 2026-10-21 <= trained_through
