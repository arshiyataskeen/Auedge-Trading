"""Which agents' votes count (the review board's decisions, or yours). Used by the live analysis and by every
backtest, so "today's rules" always means the same thing.

data/agent_votes.json  {"off": ["stophunt"], "auto_apply": true}
data/review_log.json   every change: when, by whom (review board / you / undo), what, and the evidence.
An agent that is "off" still runs and shows its view and levels; only its vote in the Chief's decision is left out.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
VOTES = DATA / "agent_votes.json"
LOG = DATA / "review_log.json"
MIN_VOTERS = 5           # the board never leaves fewer than this many voting agents


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing or half-written
        return default


def _write(path: Path, data) -> None:
    DATA.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)


def state() -> dict:
    s = _read(VOTES, {})
    return {"off": sorted(set(s.get("off", []))), "auto_apply": s.get("auto_apply", True)}


def off() -> list[str]:
    return state()["off"]


def log() -> list[dict]:
    return _read(LOG, [])


def set_auto_apply(on: bool) -> None:
    _write(VOTES, {**state(), "auto_apply": bool(on)})


def change(new_off: list[str], by: str, changes: list[dict], note: str = "", review_id: str | None = None) -> dict:
    """Save a new set of switched-off votes and log it (with the previous set, for undo)."""
    before = off()
    entry = {"t": time.time(), "by": by, "before": before, "after": sorted(set(new_off)), "changes": changes,
             "note": note, "review": review_id}
    _write(VOTES, {**state(), "off": entry["after"]})
    _write(LOG, (log() + [entry])[-200:])
    return entry


def undo() -> dict | None:
    """Put back the votes from before the last change."""
    entries = log()
    if not entries:
        return None
    last = entries[-1]
    return change(last["before"], "undo", [{"agent": a, "action": "on" if a in last["after"] else "off"}
                                           for a in set(last["before"]) ^ set(last["after"])],
                  note="Undid the change of " + time.strftime("%d %b %H:%M", time.localtime(last["t"])))


def weights(base: dict[str, float]) -> dict[str, float]:
    """Base vote weights with the switched-off agents at 0."""
    out = dict(base)
    for name in off():
        if name in out:
            out[name] = 0
    return out
