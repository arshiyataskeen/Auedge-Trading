"""NEWSINTEL_MODE = off | advisory | live (default advisory; unknown values -> advisory)."""
from __future__ import annotations

import os

from core.env import load_env

load_env()   # app.py imports the agents (which read the mode) before it loads .env

NEWS_AGENT = "news_intel"   # the display-only news agent's name (kept out of votes, dataset steps, Skeptic)
MODES = ("off", "advisory", "live")


def mode() -> str:
    m = (os.getenv("NEWSINTEL_MODE") or "advisory").strip().lower()
    return m if m in MODES else "advisory"


def effective_mode(art) -> str:
    """The requested mode, except `live` acts as `advisory` unless the exported models passed the go-live check."""
    m = mode()
    if m == "live" and not (art is not None and bool(getattr(art, "go_live", False))):
        return "advisory"
    return m
