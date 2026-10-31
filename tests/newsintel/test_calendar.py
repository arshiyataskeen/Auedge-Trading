import math

import core.newsintel.calendar as cal
from core.newsintel.calendar import FOMC_HIST, build_events, release_ts


def _rows(values, start_year=2019):
    """Monthly index levels, each first published on the 12th of the next month, never revised."""
    rows = []
    for i, v in enumerate(values):
        y, m = start_year + i // 12, i % 12 + 1
        ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
        rows.append({"date": f"{y}-{m:02d}-01", "realtime_start": f"{ny}-{nm:02d}-12",
                     "realtime_end": "9999-12-31", "value": str(v)})
    return rows


def _levels(step_cycle):
    v, out = 100.0, []
    for i in range(30):
        v *= 1 + step_cycle[i % len(step_cycle)] / 100
        out.append(round(v, 4))
    return out


def _fake(monkeypatch):
    data = {"CPIAUCSL": _rows(_levels([0.2, 0.3, 0.1, 0.4, 0.2, 0.9])),
            "CPILFESL": _rows(_levels([0.3, 0.2, 0.25, 0.3, 0.2, 0.1]))}

    def fetch(series, offline=False):
        if series not in data:
            raise RuntimeError("no data")
        return data[series]

    monkeypatch.setattr(cal, "fetch_vintages", fetch)
    # kinds without fixture data are skipped
    monkeypatch.setattr(cal, "RELEASES", {"CPI": cal.RELEASES["CPI"]})
    return data


def test_release_time_dst():
    assert release_ts("2024-01-11", 8, 30) == 1704979800
    assert release_ts("2024-07-11", 8, 30) == 1720701000


def test_fomc_list_complete():
    assert len(FOMC_HIST) == 41
    assert len({d for d, _, _ in FOMC_HIST}) == 41
    assert all("2020-01-01" <= d <= "2024-12-31" for d, _, _ in FOMC_HIST)
    assert ("2020-03-15", 17, 0) in FOMC_HIST
    assert ("2020-03-03", 10, 0) in FOMC_HIST
    for y, n in ((2020, 9), (2021, 8), (2022, 8), (2023, 8), (2024, 8)):
        assert sum(d.startswith(str(y)) for d, _, _ in FOMC_HIST) == n


def test_build_events_groups_components(monkeypatch):
    _fake(monkeypatch)
    ev = [e for e in build_events(since="2020-01-01") if e.kind == "CPI"]
    assert ev and len({e.t for e in ev}) == len(ev)
    last = ev[-1]
    assert [c.series for c in last.components] == ["CPIAUCSL", "CPILFESL"]
    head = last.components[0]
    assert head.headline and not last.components[1].headline
    assert head.surprise_z is not None and last.surprise_z == head.surprise_z
    assert last.surprise_z != last.components[1].surprise_z
    assert last.t == release_ts("2021-07-12", 8, 30)


def test_events_before_since_dropped(monkeypatch):
    _fake(monkeypatch)
    ev = build_events(since="2021-01-01")
    macro = [e for e in ev if e.components]
    assert macro and all(e.t >= release_ts("2021-01-01", 0, 0) for e in ev)
    assert min(e.t for e in macro) >= release_ts("2021-01-01", 0, 0)
    assert [e.t for e in ev] == sorted(e.t for e in ev)
    fomc = [e for e in ev if e.kind == "FOMC"]
    assert fomc and all(e.components == [] and e.surprise_z is None for e in fomc)
    assert not any(math.isnan(e.t) for e in ev)


def test_same_day_observations_latest_is_live(monkeypatch):
    # after a shutdown, Oct and Nov payrolls come out together on 2025-12-16
    rows = []
    v = 150000.0
    for i in range(36):
        y, m = 2023 + i // 12, i % 12 + 1
        v += 100 + 37 * (i % 5)
        ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
        rel = f"{ny}-{nm:02d}-05"
        if (y, m) in ((2025, 10), (2025, 11)):
            rel = "2025-12-16"
        rows.append({"date": f"{y}-{m:02d}-01", "realtime_start": rel,
                     "realtime_end": "9999-12-31", "value": str(v)})
    monkeypatch.setattr(cal, "fetch_vintages", lambda s, offline=False: rows)
    monkeypatch.setattr(cal, "RELEASES", {"NFP": {"name": "NFP", "time": (8, 30),
                                                    "series": [("PAYEMS", "diff", 1, True)]}})
    ev = [e for e in build_events(since="2025-01-01") if e.kind == "NFP"]
    day = [e for e in ev if e.t == release_ts("2025-12-16", 8, 30)]
    assert len(day) == 1
    comps = day[0].components
    assert len(comps) == 2
    live = [c for c in comps if not c.stale]
    stale = [c for c in comps if c.stale]
    assert len(live) == 1 and len(stale) == 1
    assert live[0].headline and not stale[0].headline
    assert live[0].obs_date == "2025-11-01" and stale[0].obs_date == "2025-10-01"
    assert day[0].surprise_z == live[0].surprise_z
    val = lambda i: float(rows[i]["value"])  # rows[33] = Oct 2025, rows[34] = Nov 2025
    assert live[0].actual == val(34) - val(33) and stale[0].actual == val(33) - val(32)
    # store headline columns describe the newest print
    from core.newsintel.store import _event_row
    row = _event_row(day[0])
    assert row[3] == live[0].actual and row[7] == live[0].surprise_z


def test_gdp_is_real():
    assert cal.RELEASES["GDP"]["series"] == [("GDPC1", "saar_qoq", 1, True)]
