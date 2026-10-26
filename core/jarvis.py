"""Jarvis: answers the trader's questions about the CURRENT analysis, using every agent's findings.

Claude gets the latest analysis as facts (Chief plan, today's trend, every agent's rows and summary, stop map,
track record) and the recent chat. It must answer only from those facts. Needs ANTHROPIC_API_KEY in .env.
"""
from __future__ import annotations

import json

from .ai_summary import MODEL

SYSTEM = (
    "You are Jarvis, the voice assistant of an XAU/USD (gold) analysis dashboard. A non-programmer trader asks "
    "you questions. You receive the dashboard's latest analysis as JSON: the Chief analyst's plan and today's "
    "trend (Daily, 4H, 1H, 15m), every agent's findings (Wyckoff, Elliott, Smart money, Price action, Trend "
    "analyst, Session and macro, Skeptic), the stop-loss map and the track record.\n"
    "Rules:\n"
    "- Answer only from the JSON. Never invent a price, level, news event or statistic. If the data does not "
    "say, reply that the dashboard does not know.\n"
    "- Trading levels come from the 15-minute analysis; mention which agent or timeframe a point comes from.\n"
    "- If agents disagree, say who and why in one sentence, then what the Chief decided.\n"
    "- If the data check failed (market closed, stale price), say clearly not to trade now.\n"
    "- Never claim certainty and never tell the trader to place an order; this is analysis, not financial advice.\n"
    "- Your reply is also read aloud: plain sentences, no markdown, no bullet points, no tables, at most 90 words "
    "unless the trader asks for detail."
)
MAX_HISTORY = 10


def facts_from(report: dict) -> str:
    c = report["chief"]
    c = c.model_dump() if hasattr(c, "model_dump") else c
    dc = report["data_check"]
    dc = dc.model_dump() if hasattr(dc, "model_dump") else dc
    facts = {
        "generated_at": str(report["generated_at"]),
        "data_check": {"headline": dc.get("headline"), "veto": dc.get("veto"), "warnings": dc.get("warnings")},
        "price": c.get("price"),
        "today": c.get("today"),
        "chief": {k: c.get(k) for k in ("bias", "confidence", "htf_label", "intraday_label", "headline", "verdict",
                                        "weighted_score", "timeframes", "plan", "buy_zone", "sell_zone",
                                        "recent_hunt", "reasons")},
        "stops_above": c.get("stops_above"),
        "stops_below": c.get("stops_below"),
        "agents": [{"name": a["label"], "status": a["status"], "bias": a.get("bias_label") or a["bias"],
                    "confidence": a["confidence"], "findings": a.get("rows"), "summary": a.get("summary"),
                    "levels": a.get("levels"), "warnings": a.get("warnings")} for a in report["agents"]],
        "track_record": report.get("track"),
    }
    return json.dumps(facts, default=str)


def clean_history(history: list) -> list[dict]:
    """Keep the last few text turns, alternating user/assistant and starting with the user."""
    out: list[dict] = []
    for m in history[-MAX_HISTORY:]:
        role, text = m.get("role"), str(m.get("content", "")).strip()[:2000]
        if role not in ("user", "assistant") or not text:
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n" + text
        else:
            out.append({"role": role, "content": text})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


async def ask(question: str, history: list, report: dict) -> tuple[bool, str]:
    try:
        import anthropic
    except ImportError:
        return False, "The Claude package is not installed. Close the dashboard and start run.bat again."
    messages = clean_history(history)
    if messages and messages[-1]["role"] == "user":
        messages.pop()
    messages.append({"role": "user", "content": question.strip()[:2000]})
    try:
        client = anthropic.AsyncAnthropic(timeout=90.0)
        response = await client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": "claude-opus-4-8"}],
            system=[{"type": "text", "text": SYSTEM},
                    {"type": "text", "text": "Latest analysis:\n" + facts_from(report),
                     "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
    except anthropic.AuthenticationError:
        return False, "My Claude key is not valid. Check ANTHROPIC_API_KEY in the .env file."
    except anthropic.RateLimitError:
        return False, "Too many questions right now. Try again in a minute."
    except anthropic.APIConnectionError:
        return False, "I cannot reach Claude. Check your internet connection."
    except anthropic.APIStatusError as e:
        print(f"[jarvis] Claude call failed: {e}")
        return False, f"Claude returned an error ({e.status_code}). Try again shortly."
    except Exception as e:  # noqa: BLE001 - e.g. no credentials configured at all
        print(f"[jarvis] {type(e).__name__}: {e}")
        return False, ("I need a Claude API key to answer questions. Copy .env.example to .env, put your key after "
                       "ANTHROPIC_API_KEY=, then restart the dashboard. The spoken briefing works without it.")
    if response.stop_reason == "refusal":
        return False, "I can't answer that one. Try asking about the trend, the plan or the levels."
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return bool(text), text or "I have no answer for that."
