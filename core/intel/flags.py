"""Runtime feature flags: data/intel_flags.json {"ALIGN": {"on","by","at","note"}}.

Read at call time. Missing file/key = off. Env INTEL_<NAME>=on|off overrides the file.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "data" / "intel_flags.json"
_ON, _OFF = ("on", "1", "true", "yes"), ("off", "0", "false", "no")


def all_flags() -> dict:
    try:
        d = json.loads(PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def flag(name: str) -> bool:
    name = name.upper()
    env = os.environ.get(f"INTEL_{name}", "").strip().lower()
    if env in _ON:
        return True
    if env in _OFF:
        return False
    v = all_flags().get(name)
    return bool(isinstance(v, dict) and v.get("on"))


def set_flag(name: str, on: bool, by: str = "user", note: str = "") -> dict:
    name = name.upper()
    d = all_flags()
    d[name] = {"on": bool(on), "by": by, "at": time.time(), "note": note}
    PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(PATH.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
        os.replace(tmp, PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return d[name]
