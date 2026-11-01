"""The news agent's optional vote (review board controlled, OFF by default).

The agent always reports WAIT; its candidate vote sits in extra["vote"]. `promote` turns it into the agent's bias only
when the Chief gives the agent a weight above 0, so with the vote off everything is exactly as before."""
from __future__ import annotations

from core.models import AgentResult
from core.newsintel.mode import NEWS_AGENT

MIN_CHANCE = 0.45
WEIGHT_ON = 1.0


def news_vote(intel) -> dict:
    """{"bias","confidence"} from the advisory chances: only inside an event window (phase pre/post), only when
    max(up, down) >= 0.45 and the model is not uncertain; otherwise WAIT."""
    wait = {"bias": "WAIT", "confidence": 0}
    try:
        p = intel.probs
        if intel.phase not in ("pre", "post") or not intel.event or not p or intel.uncertain:
            return wait
        up, down = float(p.get("up", 0)), float(p.get("down", 0))
        top = max(up, down)
        if top < MIN_CHANCE or up == down:
            return wait
        return {"bias": "BUY" if up > down else "SELL", "confidence": int(round(100 * top))}
    except Exception:  # noqa: BLE001
        return wait


def promote(results: list[AgentResult], weights: dict[str, float]) -> list[AgentResult]:
    """Copy of results where the news agent carries its candidate vote, if (and only if) its weight is above 0."""
    if weights.get(NEWS_AGENT, 0) <= 0:
        return results
    out = []
    for r in results:
        v = (r.extra or {}).get("vote") if r.agent == NEWS_AGENT and r.status == "OK" else None
        if v and v.get("bias") in ("BUY", "SELL"):
            r = r.model_copy(update={"bias": v["bias"], "confidence": int(v["confidence"]),
                                     "bias_label": v["bias"]})
        out.append(r)
    return out
