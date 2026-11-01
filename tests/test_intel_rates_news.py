import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from core.intel import rates, news_extra


def rows(vals):
    return [{"date": d, "realtime_start": d, "realtime_end": "9999-12-31", "value": v} for d, v in vals]


DGS = rows([("2026-10-26", "4.10"), ("2026-10-27", "4.12"), ("2026-10-28", "4.13"), ("2026-10-29", "4.14"),
            ("2026-10-30", "4.15"), ("2026-11-02", "4.21")])
DFI = rows([("2026-10-26", "1.90"), ("2026-10-27", "1.91"), ("2026-10-28", "1.92"), ("2026-10-29", "1.93"),
            ("2026-10-30", "1.91"), ("2026-11-02", "1.95")])


@pytest.fixture
def fred(monkeypatch):
    calls = []

    def fake(series, offline=False):
        calls.append((series, offline))
        return {"DGS10": DGS, "DFII10": DFI}[series]
    monkeypatch.setattr(rates.fred, "fetch_vintages", fake)
    return calls


def ts(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


def test_latest_and_changes(fred):
    r = rates.snapshot(ts("2026-11-02T20:00:00"), offline=True)
    assert r["y10"] == 4.21 and r["real"] == 1.95
    assert r["y10_d1"] == pytest.approx(0.06) and r["y10_d5"] == pytest.approx(0.11)
    assert r["real_d1"] == pytest.approx(0.04)


def test_text(fred):
    assert rates.text(ts("2026-11-02T20:00:00"), offline=True) == "10y yield 4.21% (+0.06 today), real yield 1.95% (+0.04)"


def test_asof_ignores_future(fred):
    assert rates.snapshot(ts("2026-10-28T20:00:00"), offline=True)["y10"] == 4.13


def test_old_context_never_online(fred):
    rates.snapshot(ts("2026-10-28T20:00:00"), offline=False, now=ts("2026-11-02T20:00:00"))
    assert fred and all(off for _, off in fred)


def test_recent_context_may_go_online(fred):
    now = ts("2026-11-02T20:00:00")
    rates.snapshot(now - 60, offline=False, now=now)
    assert fred and all(not off for _, off in fred)


def test_failure_returns_none(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no")
    monkeypatch.setattr(rates.fred, "fetch_vintages", boom)
    assert rates.snapshot(None, offline=True) is None and rates.text(None, offline=True) == ""


EVS = [{"t": 1000000, "name": "ISM Manufacturing PMI"}, {"t": 2000000, "name": "Unemployment Claims"},
       {"t": 3000000, "name": "Fed Chair Powell Speaks"}, {"t": 4000000, "name": "FOMC Member Waller Speaks"},
       {"t": 5000000, "name": "FOMC Statement"}, {"t": 6000000, "name": "JOLTS Job Openings"}]


def test_classify():
    k = news_extra.kind
    assert k("ISM Manufacturing PMI") == "ISM" and k("Unemployment Claims") == "CLAIMS"
    assert k("Fed Chair Powell Speaks") == "FEDSPEAK" and k("FOMC Member Waller Speaks") == "FEDSPEAK"
    assert k("FOMC Statement") is None and k("ISM Services PMI") is None and k("JOLTS Job Openings") is None


def test_blackout_window(monkeypatch):
    monkeypatch.setenv("INTEL_NEWS_EXTRA", "on")
    b = news_extra.extra_blackout(3000000 - 29 * 60, events=EVS)
    assert b["kind"] == "FEDSPEAK" and b["t"] == 3000000
    assert news_extra.extra_blackout(3000000 + 29 * 60, events=EVS)
    assert news_extra.extra_blackout(3000000 + 31 * 60, events=EVS) is None
    assert news_extra.extra_blackout(5000000, events=EVS) is None
    assert news_extra.extra_blackout(6000000, events=EVS) is None


def test_flag_off(monkeypatch):
    monkeypatch.setenv("INTEL_NEWS_EXTRA", "off")
    assert news_extra.extra_blackout(1000000, events=EVS) is None


def test_real_fixture_titles(monkeypatch):
    monkeypatch.setenv("INTEL_NEWS_EXTRA", "on")
    week = json.loads(Path("data/news_week.json").read_text())["week"]
    ism = [w for w in week if w["name"] == "ISM Manufacturing PMI"]
    assert ism
    assert news_extra.extra_blackout(ism[0]["t"], events=news_extra.load_events())["kind"] == "ISM"
