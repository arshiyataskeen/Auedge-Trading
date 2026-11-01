"""Extra no-trade news kinds beyond CPI/NFP/FOMC: ISM manufacturing PMI, jobless claims, Fed speeches.

Matched by ForexFactory titles from the saved calendar copies. Same window rules as core.news (30 min each side).
Active only when flag INTEL_NEWS_EXTRA is on (missing flags module = off).
"""
from __future__ import annotations

import json
import re

from core import news

_RULES = [("ISM", re.compile(r"^ISM Manufacturing PMI", re.I)),
          ("CLAIMS", re.compile(r"^(Unemployment|Initial Jobless) Claims", re.I)),
          ("FEDSPEAK", re.compile(r"^(Fed Chair|FOMC Member|Fed Governor|Fed Vice Chair)\b.*\bSpeaks\b", re.I))]


def _on() -> bool:
    try:
        from core.intel.flags import flag
        return flag("NEWS_EXTRA")
    except Exception:  # noqa: BLE001
        return False


def kind(name: str) -> str | None:
    for k, rx in _RULES:
        if rx.search(name or ""):
            return k
    return None


def load_events() -> list[dict]:
    """Extra-kind events from the saved week copy, the event store and the in-memory feed."""
    src: list[dict] = []
    try:
        src += json.loads(news.WEEK_CACHE.read_text())["week"]
    except Exception:  # noqa: BLE001
        pass
    src += news._stored() + list(news._mem.get("week") or [])
    seen, out = set(), []
    for e in src:
        k = kind(e.get("name", ""))
        if k and (e["t"], k) not in seen:
            seen.add((e["t"], k))
            out.append({"t": e["t"], "name": e["name"], "kind": k})
    return sorted(out, key=lambda x: x["t"])


def extra_blackout(ts: float, events: list[dict] | None = None) -> dict | None:
    """The extra event whose window contains ts, or None (also None when the flag is off)."""
    if not _on():
        return None
    for e in (load_events() if events is None else events):
        k = kind(e.get("name", ""))
        if not k:
            continue
        a, b = news.window({"t": e["t"], "kind": k})
        if a <= ts <= b:
            return {"t": e["t"], "name": e["name"], "kind": k}
    return None
