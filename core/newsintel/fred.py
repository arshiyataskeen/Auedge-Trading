"""Economic release values as first published, from FRED/ALFRED vintage data.

ALFRED keeps every revision of each data point with the dates it was valid. The value
that moved the market is the one published on release day, so each release is rebuilt
from the snapshot valid on that day, not from today's revised numbers.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx

from core.env import load_env

DATA = Path(__file__).resolve().parent.parent.parent / "data"
CACHE = DATA / "news_intel" / "fred"
URL = "https://api.stlouisfed.org/fred/series/observations"
MAX_AGE = 24 * 3600
START = "2014-01-01"
PAGE = 100000


@dataclass
class Release:
    """One release: observation date, day first published, value and the prior release's value.

    actual is None when it cannot be a one-period change: the period before it was never
    published (e.g. no October 2025 CPI after the shutdown), so a "m/m" would span two months.
    """
    obs_date: str
    release_date: str
    actual: float | None
    previous: float | None


def _download(series: str, key: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        params = {"series_id": series, "api_key": key, "file_type": "json",
                  "realtime_start": START, "realtime_end": "9999-12-31",
                  "observation_start": START, "limit": PAGE, "offset": offset}
        fail = None
        try:
            r = httpx.get(URL, params=params, timeout=60)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            fail = f"HTTP {e.response.status_code}"
        except httpx.RequestError as e:
            fail = type(e).__name__
        if fail:
            # raised outside the except block: httpx messages carry the full URL (with the api key)
            # and would otherwise stay reachable as the exception's context
            raise RuntimeError(f"FRED request for {series} failed: {fail}")
        body = r.json()
        obs = body.get("observations", [])
        rows += obs
        offset += len(obs)
        if not obs or offset >= int(body.get("count", offset)):
            break
    return [{k: o[k] for k in ("date", "realtime_start", "realtime_end", "value")}
            for o in rows if o["value"] != "."]


def fetch_vintages(series: str, offline: bool = False) -> list[dict]:
    """Return all vintage rows of a series; cached for 24 hours in CACHE/<series>.json."""
    f = CACHE / f"{series}.json"
    if f.exists() and (offline or time.time() - f.stat().st_mtime < MAX_AGE):
        return json.loads(f.read_text())
    load_env()
    key = os.environ.get("FRED_API_KEY")
    if offline or not key:
        if f.exists():  # stale cache beats nothing when there is no key
            return json.loads(f.read_text())
        raise RuntimeError(f"FRED_API_KEY is not set and there is no cached copy of {series}")
    rows = _download(series, key)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows))
    tmp.replace(f)  # atomic: a reader never sees half of it
    return rows


def _transform(kind: str, v: float, prev: float | None) -> float | None:
    if kind == "level":
        return v
    if prev is None or prev == 0:
        return None
    if kind == "pct_mom":
        return 100 * (v / prev - 1)
    if kind == "diff":
        return v - prev
    if kind == "saar_qoq":
        return 100 * ((v / prev) ** 4 - 1)
    raise ValueError(f"unknown transform {kind!r}")


def _freq(dates: list[str]) -> str:
    """'weekly', 'monthly' or 'quarterly' from the smallest spacing of the observation dates
    (missing periods only ever widen a gap)."""
    if len(dates) < 2:
        return "monthly"
    g = min((date.fromisoformat(b) - date.fromisoformat(a)).days for a, b in zip(dates, dates[1:]))
    return "weekly" if g <= 10 else "monthly" if g <= 45 else "quarterly"


def _period_before(d: str, freq: str) -> str:
    """The observation date of the period immediately before d."""
    x = date.fromisoformat(d)
    if freq == "weekly":
        return (x - timedelta(days=7)).isoformat()
    months = 1 if freq == "monthly" else 3
    y, m = divmod(x.year * 12 + x.month - 1 - months, 12)
    return date(y, m + 1, x.day).isoformat()


def first_releases(rows: list[dict], transform: str) -> list[Release]:
    """Each observation's value as first published, sorted by release date."""
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        if r["value"] == ".":
            continue
        by_date.setdefault(r["date"], []).append(r)
    dates = sorted(by_date)
    freq = _freq(dates)

    def at(date: str, v: str) -> float | None:
        # the value valid on day v (rs <= v <= re)
        for r in by_date.get(date, []):
            if r["realtime_start"] <= v <= r["realtime_end"]:
                return float(r["value"])
        return None

    out: list[Release] = []
    adjacent: dict[str, bool] = {}  # obs date -> its prior observation is the period right before it
    for i, d in enumerate(dates):
        rel = min(r["realtime_start"] for r in by_date[d])
        cur = at(d, rel)
        adjacent[d] = bool(i) and dates[i - 1] == _period_before(d, freq)
        if cur is None:
            continue
        if transform == "level":
            out.append(Release(d, rel, cur, None))
        elif i and not adjacent[d]:
            # a period is missing: a change against the older observation is not one step
            out.append(Release(d, rel, None, None))
        else:
            prior = at(dates[i - 1], rel) if i else None
            # dropped when the prior observation has no value valid on the release date,
            # so the first observation of a non-level series is never emitted
            act = _transform(transform, cur, prior)
            if act is not None:
                out.append(Release(d, rel, act, None))
    out.sort(key=lambda x: x.release_date)
    # previous = the prior period's first-release actual (None if that period is missing)
    last: dict[str, float | None] = {}
    for r in sorted(out, key=lambda x: x.obs_date):
        r.previous = last.get(_prev_obs(dates, r.obs_date)) if adjacent[r.obs_date] else None
        last[r.obs_date] = r.actual
    return out


def _prev_obs(dates: list[str], d: str) -> str:
    i = dates.index(d)
    return dates[i - 1] if i else ""
