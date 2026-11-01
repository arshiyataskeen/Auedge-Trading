"""Pytest setup: make the repo root importable so tests can use `core` and `tools`."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_claude(monkeypatch):
    """Tests never call the real Claude API or read a developer's real key."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
