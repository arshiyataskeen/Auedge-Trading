"""10y Treasury yield (FRED DGS10) and 10y real yield (DFII10): latest value and 1/5-day change as plain text.

Uses core.newsintel.fred (atomic 24h cache). Network is only allowed when offline is False AND the context is
live (ts None or within 15 min of now); backtests and old contexts read the cache only, as of ts.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import httpx

from core.env import load_env
from core.newsintel import fred

LIVE_S = 15 * 60
MAX_AGE = 6 * 3600
OBS_START = "2024-01-01"


def _latest_rows(sid: str, offline: bool) -> list[dict]:
    """Plain (non-vintage) observations: FRED rejects the all-vintages request for daily series (HTTP 400).
    Cached atomically in the FRED cache dir as <sid>.latest.json; stale copy beats nothing."""
    f = fred.CACHE / f"{sid}.latest.json"
    if f.exists() and (offline or time.time() - f.stat().st_mtime < MAX_AGE):
        return json.loads(f.read_text())
    load_env()
    key = os.environ.get("FRED_API_KEY")
    if offline or not key:
        if f.exists():
            return json.loads(f.read_text())
        raise RuntimeError(f"no cached copy of {sid}")
    r = httpx.get(fred.URL, params={"series_id": sid, "api_key": key, "file_type": "json",
                                    "observation_start": OBS_START}, timeout=30)
    r.raise_for_status()
    rows = [{"date": o["date"], "realtime_start": o["date"], "realtime_end": "9999-12-31", "value": o["value"]}
            for o in r.json().get("observations", []) if o["value"] != "."]
    fred._write_cache(f"{sid}.latest", rows)
    return rows


def _rows(sid: str, offline: bool) -> list[dict]:
    try:
        return fred.fetch_vintages(sid, offline=offline)
    except Exception:  # noqa: BLE001 - e.g. HTTP 400 for daily series: use plain observations
        return _latest_rows(sid, offline)


def _series(sid: str, ts: float | None, offline: bool) -> list[tuple[str, float]]:
    out: dict[str, float] = {}
    for r in sorted(_rows(sid, offline), key=lambda r: r["realtime_start"]):
        try:
            out[r["date"]] = float(r["value"])   # later vintage of the same day wins
        except (ValueError, KeyError):
            continue
    pts = sorted(out.items())
    if ts is not None:
        day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
        pts = [p for p in pts if p[0] <= day]
    return pts


def snapshot(ts: float | None = None, offline: bool = False, now: float | None = None) -> dict | None:
    """{'date','y10','y10_d1','y10_d5','real','real_d1','real_d5'} as of ts, or None if no data."""
    now = time.time() if now is None else now
    off = offline or (ts is not None and now - ts > LIVE_S)
    try:
        a, b = _series("DGS10", ts, off), _series("DFII10", ts, off)
    except Exception:  # noqa: BLE001 - rates are context only, never block a decision
        return None
    if not a or not b:
        return None

    def chg(p, n):
        return round(p[-1][1] - p[-1 - n][1], 4) if len(p) > n else None
    return {"date": a[-1][0], "y10": a[-1][1], "y10_d1": chg(a, 1), "y10_d5": chg(a, 5),
            "real": b[-1][1], "real_d1": chg(b, 1), "real_d5": chg(b, 5)}


def _s(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.2f}"


def text(ts: float | None = None, offline: bool = False, now: float | None = None) -> str:
    r = snapshot(ts, offline, now)
    if not r:
        return ""
    return (f"10y yield {r['y10']:.2f}% ({_s(r['y10_d1'])} today), "
            f"real yield {r['real']:.2f}% ({_s(r['real_d1'])})")
