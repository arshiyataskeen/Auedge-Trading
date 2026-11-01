"""Non-voting agents (news_intel) must not leak into the dataset steps / CSV export."""
from __future__ import annotations

import json

from core import dataset
from core.models import AgentResult


def _res(agent, bias="WAIT", conf=0, status="OK"):
    return AgentResult(agent=agent, bias=bias, confidence=conf, status=status)


class _Plan:
    entry_lo = entry_hi = stop = be_at = t1 = side = None
    action, kind = "NO TRADE", "none"


class _Rep:
    bias, confidence, weighted_score, htf_label = "WAIT", 0, 0.0, ""
    plan, today = _Plan(), {}


def test_dataset_row_skips_non_voting_agents():
    row = dataset._row("live", None, 1.0e9, 2000.0, [_res("trend", "BUY", 60), _res("news_intel")], _Rep())
    stored = json.loads(row[-1])
    assert "trend" in stored and "news_intel" not in stored

