"""Optional: Claude writes the Chief's top-down verdict from the agents' findings.

Runs only when ANTHROPIC_API_KEY is set (in the .env file or the environment). Claude is given the
agents' numbers as facts and is told not to invent any. If anything fails, the rule-based verdict stays.
"""
from __future__ import annotations

import json
import os

MODEL = "claude-opus-5-5"
SYSTEM = (
    "You are the chief analyst of an XAU/USD (gold) analysis dashboard. You receive the findings of six "
    "analysis agents (Wyckoff, Elliott, Smart money, Price action, Session and macro, Skeptic) and a "
    "top-down bias for Daily, 4H, 1H and 15m. Write the final verdict for a non-programmer trader.\n"
    "Rules:\n"
    "- Use only the prices and facts in the input. Never invent a number or a news event.\n"
    "- Start from the higher timeframes, then explain whether the lower timeframes agree.\n"
    "- Say plainly when timeframes conflict and which one wins for a swing trade versus an intraday trade.\n"
    "- End with one line in this form: 'Verdict: WAIT/BUY/SELL at <price>, BUY only at <zone>, SELL only at <zone>.' "
    "using the zones given.\n"
    "- Never claim certainty. This is analysis, not financial advice. Prices are indicative mid-market rates.\n"
    "- At most 110 words, plain sentences, no markdown, no bullet points."
)


def enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


async def write_verdict(report: dict, agents: list[dict]) -> str | None:
    if not enabled():
        return None
    try:
        import anthropic
    except ImportError:
        return None
    facts = {
        "price": report.get("price"),
        "timeframes": report.get("timeframes"),
        "rule_based_verdict": report.get("verdict"),
        "buy_zone": report.get("buy_zone"),
        "sell_zone": report.get("sell_zone"),
        "agents": [{"name": a["label"], "bias": a.get("bias_label") or a["bias"], "status": a["status"],
                    "findings": a.get("rows"), "summary": a.get("summary")} for a in agents],
    }
    try:
        client = anthropic.AsyncAnthropic(timeout=90.0)
        response = await client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": "claude-opus-4-8"}],
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(facts, default=str)}],
        )
    except anthropic.APIError as e:
        print(f"[ai_summary] Claude call failed: {e}")
        return None
    if response.stop_reason == "refusal":
        return None
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text or None
