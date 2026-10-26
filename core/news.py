"""High-impact US news that moves gold: CPI, the jobs report (NFP) and Fed (FOMC) decisions.

No new trade from 30 minutes before to 30 minutes after CPI and NFP (08:30 New York), and from 30 minutes before
to 60 minutes after an FOMC decision (14:00 New York, followed by the press conference at 14:30).

Sources:
- Official dates below: BLS 2026 release schedule (CPI, Employment Situation) and 2027 CPI schedule
  (bls.gov/schedule), Federal Reserve FOMC calendar (federalreserve.gov). Update these lists each year.
- Live: the ForexFactory weekly calendar feed (all high-impact USD events this week, e.g. a speech by the Fed
  chair). Events seen there are kept in data/news_events.json, so the history grows over time.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

NY = ZoneInfo("America/New_York")
BEFORE_S = 30 * 60
AFTER_S = {"FOMC": 60 * 60}            # Fed: statement 14:00 + press conference; others 30 min
DEFAULT_AFTER_S = 30 * 60
FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
STORE = Path(__file__).resolve().parent.parent / "data" / "news_events.json"
FEED_MAX_AGE_S = 6 * 3600              # ForexFactory rate-limits this feed: ask rarely, keep a copy on disk
RETRY_AFTER_FAIL_S = 30 * 60
WEEK_CACHE = Path(__file__).resolve().parent.parent / "data" / "news_week.json"

CPI = ["2026-01-13", "2026-02-13", "2026-03-11", "2026-04-10", "2026-05-12", "2026-06-10", "2026-07-14",
       "2026-08-12", "2026-09-11", "2026-10-14", "2026-11-10", "2026-12-10",
       "2027-01-13", "2027-02-11", "2027-03-10", "2027-04-13", "2027-05-12", "2027-06-10", "2027-07-14",
       "2027-08-11", "2027-09-14", "2027-10-14", "2027-11-10", "2027-12-10"]
NFP = ["2026-01-09", "2026-02-11", "2026-03-06", "2026-04-03", "2026-05-08", "2026-06-05", "2026-07-02",
       "2026-08-07", "2026-09-04", "2026-10-02", "2026-11-06", "2026-12-04",
       # 2027: BLS Employment Situation schedule
       "2027-01-08", "2027-02-05", "2027-03-05", "2027-04-02", "2027-05-07", "2027-06-04", "2027-07-02",
       "2027-08-06", "2027-09-03", "2027-10-08", "2027-11-05", "2027-12-03"]
FOMC = ["2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
        "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
        # 2027 (Fed's tentative schedule; decision on the 2nd day)
        "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08"]

_mem: dict = {"at": 0.0, "events": None}


def _at_ny(day: str, hh: int, mm: int) -> int:
    d = datetime.strptime(day, "%Y-%m-%d")
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).timestamp())


def official() -> list[dict]:
    ev = [{"t": _at_ny(d, 8, 30), "name": "CPI (inflation)", "kind": "CPI"} for d in CPI]
    ev += [{"t": _at_ny(d, 8, 30), "name": "Jobs report (NFP)", "kind": "NFP"} for d in NFP]
    ev += [{"t": _at_ny(d, 14, 0), "name": "Fed decision (FOMC)", "kind": "FOMC"} for d in FOMC]
    return ev


def _stored() -> list[dict]:
    try:
        return json.loads(STORE.read_text())
    except Exception:  # noqa: BLE001 - none yet
        return []


def refresh_feed() -> None:
    """Pull this week's calendar (live app only): gold-relevant events for the News tab, and the high-impact
    USD ones remembered for the no-trade filter."""
    if "week" not in _mem:                 # first call after a restart: use the saved copy if it is recent
        try:
            saved = json.loads(WEEK_CACHE.read_text())
            _mem["week"], _mem["at"] = saved["week"], saved["fetched_at"]
        except Exception:  # noqa: BLE001 - no copy yet
            _mem["week"] = []
    if time.time() - _mem["at"] < FEED_MAX_AGE_S:
        return
    _mem["at"] = time.time()
    try:
        r = httpx.get(FEED, timeout=15)
        r.raise_for_status()
        raw = r.json()
    except Exception as e:  # noqa: BLE001 - the filter still works with the official lists and the saved copy
        print(f"[news] {type(e).__name__}: {e}")
        _mem["at"] = time.time() - FEED_MAX_AGE_S + RETRY_AFTER_FAIL_S
        return
    # Gold is priced in dollars: US data moves it most. Keep high and medium impact USD events for the News tab.
    _mem["week"] = sorted(({"t": int(datetime.fromisoformat(e["date"]).timestamp()), "name": e["title"],
                            "impact": e["impact"], "forecast": e.get("forecast", ""), "previous": e.get("previous", "")}
                           for e in raw if e.get("country") == "USD" and e.get("impact") in ("High", "Medium")),
                          key=lambda x: x["t"])
    WEEK_CACHE.parent.mkdir(exist_ok=True)
    WEEK_CACHE.write_text(json.dumps({"fetched_at": _mem["at"], "week": _mem["week"]}))
    new = [{"t": x["t"], "name": x["name"], "kind": "FEED"} for x in _mem["week"] if x["impact"] == "High"]
    known = {(x["t"], x["name"]) for x in _stored()}
    merged = _stored() + [x for x in new if (x["t"], x["name"]) not in known]
    STORE.parent.mkdir(exist_ok=True)
    STORE.write_text(json.dumps(sorted(merged, key=lambda x: x["t"])))
    _mem["events"] = None


def events() -> list[dict]:
    if _mem["events"] is None:
        ev = official()
        seen = {(x["t"] // 600) for x in ev}       # the feed repeats CPI/NFP/FOMC: keep one per 10-minute slot
        ev += [x for x in _stored() if x["t"] // 600 not in seen]
        _mem["events"] = sorted(ev, key=lambda x: x["t"])
    return _mem["events"]


def window(e: dict) -> tuple[int, int]:
    return e["t"] - BEFORE_S, e["t"] + AFTER_S.get(e["kind"], DEFAULT_AFTER_S)


def blackout(ts: float) -> dict | None:
    """The news event whose no-trade window contains ts, if any."""
    for e in events():
        a, b = window(e)
        if a <= ts <= b:
            return e
        if a > ts:
            break
    return None


def upcoming(ts: float, hours: float = 48) -> list[dict]:
    return [e for e in events() if ts - DEFAULT_AFTER_S <= e["t"] <= ts + hours * 3600]


def label(e: dict, now: float) -> str:
    ny = datetime.fromtimestamp(e["t"], NY)
    mins = int((e["t"] - now) / 60)
    when = (f"in {mins} min" if 0 <= mins < 120 else f"{-mins} min ago" if mins < 0
            else ny.strftime("%a %d %b %H:%M New York"))
    return f"{e['name']} {when}"


def week_feed() -> list[dict]:
    """This week's high and medium impact USD events from ForexFactory (empty until the first refresh)."""
    return _mem.get("week") or []
