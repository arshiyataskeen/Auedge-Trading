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


def _intel_state() -> dict:
    from core.intel.flags import all_flags
    return {k: bool(v.get("on")) for k, v in all_flags().items() if isinstance(v, dict)}


def change(new_off: list[str], by: str, changes: list[dict], note: str = "", review_id: str | None = None,
           intel_after: dict | None = None) -> dict:
    """Save a new set of switched-off votes (and, optionally, INTEL_* filter switches) and log it with the previous
    state, for undo. Votes and filters share this one log."""
    before = off()
    entry = {"t": time.time(), "by": by, "before": before, "after": sorted(set(new_off)), "changes": changes,
             "note": note, "review": review_id}
    if intel_after:
        from core.intel.flags import set_flag
        cur = _intel_state()
        entry["intel_before"] = {k: cur.get(k, False) for k in intel_after}
        entry["intel_after"] = {k: bool(v) for k, v in intel_after.items()}
        for k, v in intel_after.items():
            set_flag(k, bool(v), by, note)
    _write(VOTES, {**state(), "off": entry["after"]})
    _write(LOG, (log() + [entry])[-200:])
    return entry


def undo() -> dict | None:
    """Put back the votes from before the last change."""
    entries = log()
    if not entries:
        return None
    last = entries[-1]
    ib = last.get("intel_before") or {}
    return change(last["before"], "undo", [{"agent": a, "action": "on" if a in last["after"] else "off"}
                                           for a in set(last["before"]) ^ set(last["after"])] +
                  [{"agent": "filter:" + k, "flag": k, "action": "on" if v else "off"} for k, v in ib.items()],
                  note="Undid the change of " + time.strftime("%d %b %H:%M", time.localtime(last["t"])),
                  intel_after=ib or None)


def weights(base: dict[str, float]) -> dict[str, float]:
    """Base vote weights with the switched-off agents at 0."""
    out = dict(base)
    for name in off():
        if name in out:
            out[name] = 0
    return out
