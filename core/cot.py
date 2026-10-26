"""Weekly Commitments of Traders (CFTC, free and official) for COMEX gold: how big players are positioned.

- Speculators ("non-commercial": hedge funds, CTAs) follow trends; at extremes they are the crowd that is "all in".
- Commercials (producers, banks hedging) usually sit on the other side.
Positions are as of Tuesday and published Friday 15:30 New York, so a report only counts from Friday evening
(no look-ahead in the backtest). Cached in data/cot_gold.json, refreshed at most every 12 hours.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
GOLD_CODE = "088691"
CACHE = Path(__file__).resolve().parent.parent / "data" / "cot_gold.json"
MAX_AGE_S = 12 * 3600
PUBLISH_DELAY_S = 3 * 86400 + 21 * 3600      # Tuesday 00:00 UTC -> Friday ~21:00 UTC (after the 15:30 ET release)
LOOKBACK_WEEKS = 156                         # 3 years for the "how extreme is this" index
_mem: dict = {"at": 0.0, "rows": []}
PARAMS = {"$where": f"cftc_contract_market_code='{GOLD_CODE}'", "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": "400"}


def _parse(raw: list[dict]) -> list[dict]:
    rows = []
    for r in raw:
        try:
            d = datetime.fromisoformat(r["report_date_as_yyyy_mm_dd"][:10]).replace(tzinfo=timezone.utc)
            rows.append({"date": d.strftime("%Y-%m-%d"), "pub": int(d.timestamp()) + PUBLISH_DELAY_S,
                         "spec_long": int(float(r["noncomm_positions_long_all"])),
                         "spec_short": int(float(r["noncomm_positions_short_all"])),
                         "comm_long": int(float(r["comm_positions_long_all"])),
                         "comm_short": int(float(r["comm_positions_short_all"])),
                         "oi": int(float(r["open_interest_all"]))})
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(rows, key=lambda x: x["date"])


def _cached() -> tuple[float, list[dict]]:
    try:
        d = json.loads(CACHE.read_text())
        return d["fetched_at"], d["rows"]
    except Exception:  # noqa: BLE001 - no or broken cache
        return 0.0, []


def _store(rows: list[dict]) -> None:
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps({"fetched_at": time.time(), "rows": rows}))


async def load_async() -> list[dict]:
    """For the live app: memory -> file cache -> CFTC (on failure, keep whatever we had)."""
    if _mem["rows"] and time.time() - _mem["at"] < MAX_AGE_S:
        return _mem["rows"]
    at, rows = _cached()
    if not rows or time.time() - at > MAX_AGE_S:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(URL, params=PARAMS)
                r.raise_for_status()
                fresh = _parse(r.json())
            if fresh:
                rows = fresh
                _store(rows)
        except Exception as e:  # noqa: BLE001 - COT is optional context, never block the analysis
            print(f"[cot] {type(e).__name__}: {e}")
    _mem.update(at=time.time(), rows=rows)
    return rows


def load_sync() -> list[dict]:
    """For the backtest."""
    at, rows = _cached()
    if not rows or time.time() - at > MAX_AGE_S:
        try:
            r = httpx.get(URL, params=PARAMS, timeout=20)
            r.raise_for_status()
            fresh = _parse(r.json())
            if fresh:
                rows = fresh
                _store(rows)
        except Exception as e:  # noqa: BLE001
            print(f"[cot] {type(e).__name__}: {e}")
    return rows


def view(rows: list[dict], now_ts: float) -> dict | None:
    """Positioning as known at now_ts: speculators' net, its 3-year index (0 = most short, 100 = most long) and change."""
    known = [r for r in rows if r["pub"] <= now_ts][-LOOKBACK_WEEKS:]
    if len(known) < 26:
        return None
    nets = [r["spec_long"] - r["spec_short"] for r in known]
    lo, hi = min(nets), max(nets)
    last = known[-1]
    return {"date": last["date"], "net": nets[-1], "change": nets[-1] - nets[-2],
            "index": round(100 * (nets[-1] - lo) / (hi - lo)) if hi > lo else 50,
            "long_pct": round(100 * last["spec_long"] / max(1, last["spec_long"] + last["spec_short"])),
            "comm_net": last["comm_long"] - last["comm_short"], "weeks": len(known),
            "age_days": round((now_ts - (last["pub"] - PUBLISH_DELAY_S)) / 86400, 1)}
