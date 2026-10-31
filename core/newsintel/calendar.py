"""Calendar of high-impact US events since 2020, with a surprise score for each release.

Releases come from first-published FRED values; FOMC decisions come from a fixed list.
Components of one kind published the same day (CPI headline and core, NFP jobs and
unemployment, ...) form a single event.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from core.news import FOMC
from core.newsintel.fred import fetch_vintages, first_releases
from core.newsintel.surprise import expectations

NY = ZoneInfo("America/New_York")

# kind -> name, release time (New York) and series (id, transform, sign, headline)
RELEASES: dict[str, dict] = {
    "CPI": {"name": "CPI", "time": (8, 30),
            "series": [("CPIAUCSL", "pct_mom", 1, True), ("CPILFESL", "pct_mom", 1, False)]},
    "PPI": {"name": "PPI", "time": (8, 30), "series": [("PPIFIS", "pct_mom", 1, True)]},
    "PCE": {"name": "PCE", "time": (8, 30),
            "series": [("PCEPI", "pct_mom", 1, True), ("PCEPILFE", "pct_mom", 1, False)]},
    "NFP": {"name": "Non-Farm Payrolls", "time": (8, 30),
            "series": [("PAYEMS", "diff", 1, True), ("UNRATE", "level", -1, False)]},
    # advance estimate only: first_releases keeps the first publication of each quarter
    "GDP": {"name": "GDP (advance)", "time": (8, 30), "series": [("GDP", "saar_qoq", 1, True)]},
    "RETAIL": {"name": "Retail Sales", "time": (8, 30), "series": [("RSAFS", "pct_mom", 1, True)]},
    "CLAIMS": {"name": "Jobless Claims", "time": (8, 30), "series": [("ICSA", "level", -1, True)]},
}

# FOMC decisions 2020-2024 (date, hour, minute); 14:00 unless an emergency meeting
FOMC_HIST: list[tuple[str, int, int]] = [
    ("2020-01-29", 14, 0), ("2020-03-03", 10, 0), ("2020-03-15", 17, 0), ("2020-04-29", 14, 0),
    ("2020-06-10", 14, 0), ("2020-07-29", 14, 0), ("2020-09-16", 14, 0), ("2020-11-05", 14, 0),
    ("2020-12-16", 14, 0),
    ("2021-01-27", 14, 0), ("2021-03-17", 14, 0), ("2021-04-28", 14, 0), ("2021-06-16", 14, 0),
    ("2021-07-28", 14, 0), ("2021-09-22", 14, 0), ("2021-11-03", 14, 0), ("2021-12-15", 14, 0),
    ("2022-01-26", 14, 0), ("2022-03-16", 14, 0), ("2022-05-04", 14, 0), ("2022-06-15", 14, 0),
    ("2022-07-27", 14, 0), ("2022-09-21", 14, 0), ("2022-11-02", 14, 0), ("2022-12-14", 14, 0),
    ("2023-02-01", 14, 0), ("2023-03-22", 14, 0), ("2023-05-03", 14, 0), ("2023-06-14", 14, 0),
    ("2023-07-26", 14, 0), ("2023-09-20", 14, 0), ("2023-11-01", 14, 0), ("2023-12-13", 14, 0),
    ("2024-01-31", 14, 0), ("2024-03-20", 14, 0), ("2024-05-01", 14, 0), ("2024-06-12", 14, 0),
    ("2024-07-31", 14, 0), ("2024-09-18", 14, 0), ("2024-11-07", 14, 0), ("2024-12-18", 14, 0),
]


@dataclass
class Component:
    """One series of an event: values, expectation and signed surprise z."""
    series: str
    actual: float
    previous: float | None
    expected: float | None
    sigma: float | None
    surprise_z: float | None
    headline: bool


@dataclass
class Event:
    kind: str
    name: str
    t: int  # unix seconds
    components: list[Component] = field(default_factory=list)

    @property
    def surprise_z(self) -> float | None:
        """The headline component's z (None for FOMC, which has no components)."""
        for c in self.components:
            if c.headline:
                return c.surprise_z
        return None


def release_ts(day: str, h: int, m: int) -> int:
    """New York wall time on `day` as unix seconds (DST aware)."""
    y, mo, d = map(int, day.split("-"))
    return int(datetime(y, mo, d, h, m, tzinfo=NY).timestamp())


def build_events(since: str = "2020-01-01", offline: bool = False) -> list[Event]:
    """All events with release date >= since, sorted by time.

    Surprises are fitted on each series' whole history (from 2014) so the model is warm
    at `since`; only events on or after `since` are returned.
    """
    events: list[Event] = []
    for kind, spec in RELEASES.items():
        h, m = spec["time"]
        by_day: dict[str, list[Component]] = {}
        for sid, transform, sign, headline in spec["series"]:
            rels = first_releases(fetch_vintages(sid, offline=offline), transform)
            for r, s in zip(rels, expectations(rels, sign)):
                if r.release_date >= since:
                    by_day.setdefault(r.release_date, []).append(
                        Component(sid, r.actual, r.previous, s.expected, s.sigma, s.z, headline))
        for day, comps in by_day.items():
            events.append(Event(kind, spec["name"], release_ts(day, h, m), comps))
    seen: set[int] = set()
    for day, h, m in FOMC_HIST + [(d, 14, 0) for d in FOMC]:
        t = release_ts(day, h, m)
        if day >= since and t not in seen:
            seen.add(t)
            events.append(Event("FOMC", "FOMC Decision", t, []))
    events.sort(key=lambda e: e.t)
    return events
