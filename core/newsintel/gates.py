"""AVOID gates: reasons not to open a NEW trade right now (never a reason to open one).

Checked in this order: calendar (no-trade window around a high-impact release, live list plus the historical
releases in news_intel.db), volatility (last finished 5-minute candle abnormally large), spread (much wider than
usual), uncertain (the news models are unsure, only around a release). Without exported models only the calendar
gate can fire. The 5-minute data is futures and arrives about 10 minutes late, so volatility gates fire 10-15
minutes after the spike starts."""
from __future__ import annotations

import sqlite3

from core import news
from core.newsintel import store

DB = store.DB
SPREAD_X = 3.0           # spread above this many times its median blocks
PRE_S = 2 * 3600         # "uncertain" only counts this close before a release (or after it)
SLOT_S = 600
LATE = "The 5-minute data is about 10 minutes behind, so this warning arrives 10-15 minutes late."
_cache: dict = {}


def _historical() -> list[dict]:
    try:
        mtime = DB.stat().st_mtime
    except OSError:
        return []
    if _cache.get("k") != (str(DB), mtime):
        try:
            with store.connect(DB) as con:
                rows = con.execute("SELECT kind, name, t FROM events").fetchall()
            _cache.update(k=(str(DB), mtime), rows=[{"t": int(r["t"]), "kind": r["kind"], "name": r["name"]}
                                                    for r in rows])
        except sqlite3.Error:
            return []
    return _cache["rows"]


def calendar_events() -> list[dict]:
    """Live/official events plus historical ones, one per 10-minute slot (the live list wins), sorted by time."""
    out: dict[int, dict] = {}
    for e in _historical():
        out[e["t"] // SLOT_S] = e
    for e in news.events():
        out[e["t"] // SLOT_S] = e
    return sorted(out.values(), key=lambda e: e["t"])


def blackout(ts: float) -> dict | None:
    """The event whose no-trade window (core.news.window) contains ts, over the combined calendar."""
    for e in calendar_events():
        a, b = news.window(e)
        if a <= ts <= b:
            return e
        if a > ts:
            break
    return None


def avoid(ts: float, m5: list | None, spread: float | None, spread_median: float | None, intel: dict | None,
          art) -> tuple[str, str] | None:
    ev = blackout(ts)
    if ev:
        return "calendar", (f"{ev.get('name', ev['kind'])} is inside its no-trade window; spreads widen and price "
                            f"whips both ways.")
    if art is None:
        return None
    p99 = getattr(art, "m5_range_p99", None)
    if m5 and p99:
        from core.newsintel.live import m5_ratio
        r = m5_ratio(m5)
        if r is not None and r > p99:
            return "volatility", (f"The last 5-minute candle was {r:.1f}x its normal range, unusually large. {LATE}")
    if spread and spread_median and spread > SPREAD_X * spread_median:
        return "spread", f"The spread is {spread / spread_median:.1f}x its usual size: entering now costs too much."
    if intel and intel.get("uncertain"):
        phase, e = intel.get("phase"), intel.get("event") or {}
        inside = phase == "post" or (phase == "pre" and 0 <= e.get("t", 1e18) - ts <= PRE_S)
        if inside:
            return "uncertain", "The news models are unsure about this release: stay out until it settles."
    return None
