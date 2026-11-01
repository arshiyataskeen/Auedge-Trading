"""Adds the news view to the Chief's report. advisory: one reason line, nothing else. live (only when the exported
models passed the go-live check): may also lower confidence, turn a weak call into WAIT, or raise confidence a little.
Never creates a trade."""
from __future__ import annotations

from agents.chief import MAX_CONFIDENCE, TradePlan
from core.newsintel.mode import NEWS_AGENT, mode

WEAK_P = 0.40
STRONG_P = 0.55
BOOST = 5
UNCERTAIN_PENALTY = 10


def _line(ex: dict) -> str | None:
    ev = ex.get("event")
    probs = ex.get("probs")
    move = ex.get("expected_move")
    if not ev or move is None:
        return None
    kind = ev.get("kind") or ev.get("name") or "the release"
    when = "after" if ex.get("phase") == "post" else "before"
    s = f"News (advisory): {when} {kind} expect about ${move:.2f} in the first hour"
    rng = ex.get("expected_range")
    if rng and len(rng) == 2:
        s += f" (range {rng[0]:,.2f}\u2013{rng[1]:,.2f})"
    if probs:
        s += (f"; chances up {100 * probs.get('up', 0):.0f}% / flat {100 * probs.get('side', 0):.0f}% / "
              f"down {100 * probs.get('down', 0):.0f}%")
    sim = ex.get("similar") or []
    if sim:
        c = {k: sum(1 for x in sim if x.get("label") == k) for k in ("up", "side", "down")}
        s += (f"; {len(sim)} similar past releases moved up {c['up']} / flat {c['side']} / down {c['down']}")
    return s + "."


def apply_news(rep, news) -> None:
    if news is None or mode() == "off":
        return
    ex = getattr(news, "extra", None) or {}
    eff = ex.get("mode")
    if eff not in ("advisory", "live"):
        return
    line = _line(ex)
    if line is None:
        return
    rep.reasons = [*rep.reasons, line]
    if eff != "live":
        return
    probs = ex.get("probs")
    if not probs or rep.bias not in ("BUY", "SELL") or rep.plan.kind == "none":
        return
    p = probs.get("up" if rep.bias == "BUY" else "down")
    if p is None:
        return
    if p < WEAK_P:
        rep.bias = "WAIT"
        rep.plan = TradePlan(kind="none", action="WAIT (news view disagrees)",
                             steps=["The news view disagrees with this call: wait."])
        rep.reasons.append("News (live): the chance of this side is low, so the call is turned into WAIT.")
        return
    conf = rep.confidence
    if p >= STRONG_P:
        conf = min(MAX_CONFIDENCE, conf + BOOST)
    if ex.get("uncertain"):
        conf = max(0, conf - UNCERTAIN_PENALTY)
    rep.confidence = conf
    rep.confidence_word = "High" if conf >= 70 else "Medium" if conf >= 50 else "Low"


def apply_from_results(rep, results) -> None:
    """Find the news agent's result among the agents' results and apply it (never raises: the Chief must not break)."""
    try:
        apply_news(rep, next((r for r in results if r.agent == NEWS_AGENT), None))
    except Exception as e:  # noqa: BLE001
        import sys
        print(f"[news_intel] chief hook skipped: {type(e).__name__}: {e}", file=sys.stderr)
