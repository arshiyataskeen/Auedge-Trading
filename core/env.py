"""Reads optional settings from a .env file next to app.py (e.g. ANTHROPIC_API_KEY=...)."""
import os
from pathlib import Path


def load_env() -> None:
    f = Path(__file__).resolve().parent.parent / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
