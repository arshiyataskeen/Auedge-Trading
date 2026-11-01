"""Plain-language Claude note for a news event. Display only: the agent never waits for Claude (agents time out
after 10 s). It shows `cached_note`, and `refresh_note` (scheduled in the background, once per `note_key`) fills the
cache from Claude. The prompt carries only `Intel` facts. No API key, no `anthropic`, any failure -> no note."""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from core import ai_summary

NOTES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "news_intel" / "notes.json"
MAX_NOTES = 50
_cache: dict[str, str] = {}
_miss: dict[str, float] = {}      # note_key -> monotonic time of a notes.json miss
MISS_TTL_S = 60.0
MAX_WORDS = 90
SYSTEM = (
    "You explain a gold (XAU/USD) news situation to a non-programmer trader. You receive facts about one US "
    "economic release: the event, the phase (pre = before, post = after), the actual surprise, the typical "
    "first-hour move, advisory chances for up/side/down, and similar past releases with dates and moves.\n"
    "Rules:\n"
    "- Plain words, at most 70 words, no markdown, no bullet points.\n"
    "- Use only the numbers and events in the input. Never invent a number or an event.\n"
    "- Say the chances are advisory and not a trade signal.\n"
    "- Give no trading advice."
)


def note_key(intel) -> str | None:
    ev = getattr(intel, "event", None)
    if intel.phase == "none" or not ev:
        return None
    z = intel.surprise_z
    return f"{int(ev['t'])}|{intel.phase}|{'' if z is None else round(float(z), 1)}"


def _load() -> dict[str, str]:
    try:
        d = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(notes: dict[str, str]) -> None:
    NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    keep = dict(list(notes.items())[-MAX_NOTES:])
    fd, tmp = tempfile.mkstemp(dir=NOTES_PATH.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(keep, f)
        os.replace(tmp, NOTES_PATH)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def cached_note(intel) -> str | None:
    key = note_key(intel)
    if key is None:
        return None
    if key not in _cache and time.monotonic() - _miss.get(key, -1e9) >= MISS_TTL_S:
        v = _load().get(key)
        if v:
            _cache[key] = v
        else:
            _miss[key] = time.monotonic()
    return _cache.get(key)


def facts(intel) -> dict:
    """Only fields of Intel the note may use (no model internals, features or notes)."""
    d = dataclasses.asdict(intel)
    return {k: d[k] for k in ("phase", "event", "others", "surprise_z", "expected_move", "probs", "similar",
                              "uncertain")}


async def refresh_note(intel) -> None:
    try:
        key = note_key(intel)
        if key is None or not ai_summary.enabled():
            return
        import anthropic
        payload = dict(facts(intel), chances_label="advisory, not a trade signal")
        client = anthropic.AsyncAnthropic(timeout=60.0)
        response = await client.beta.messages.create(
            model=ai_summary.MODEL,
            max_tokens=1500,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": "claude-opus-4-8"}],
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
        )
        if response.stop_reason == "refusal":
            return
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if not text:
            return
        if len(text.split()) > MAX_WORDS:
            print(f"[news_explain] note rejected: over {MAX_WORDS} words", file=sys.stderr)
            return
        _cache[key] = text
        notes = _load()
        notes.pop(key, None)
        notes[key] = text
        _save(notes)
    except Exception as e:  # noqa: BLE001 - a display note must never break the app
        print(f"[news_explain] note failed: {type(e).__name__}", file=sys.stderr)
