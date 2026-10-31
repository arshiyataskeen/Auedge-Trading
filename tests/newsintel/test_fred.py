import json
from pathlib import Path

import httpx
import pytest

from core.newsintel import fred

FIX = Path(__file__).parent / "fixtures" / "alfred_payems.json"


def _rows():
    return json.loads(FIX.read_text())["observations"]


def _row(date, start, value, end="9999-12-31"):
    return {"date": date, "realtime_start": start, "realtime_end": end, "value": str(value)}


def test_first_release_uses_vintage_not_revision():
    out = {r.obs_date: r for r in fred.first_releases(_rows(), "diff")}
    r = out["2024-01-01"]
    assert r.release_date == "2024-02-02"
    assert r.actual == 353.0
    assert r.previous is None or isinstance(r.previous, float)


def test_pct_mom_and_saar():
    m = fred.first_releases([_row("2024-01-01", "2024-02-01", 100), _row("2024-02-01", "2024-03-01", 100.3)], "pct_mom")
    assert m[-1].actual == pytest.approx(0.3, abs=1e-9)
    q = fred.first_releases([_row("2024-01-01", "2024-04-25", 100), _row("2024-04-01", "2024-07-25", 101)], "saar_qoq")
    assert q[-1].actual == pytest.approx(4.06, abs=0.01)
    assert q[-1].release_date == "2024-07-25"


def test_previous_is_prior_first_release_and_level():
    rows = [_row("2024-01-01", "2024-02-01", 1.0), _row("2024-02-01", "2024-03-01", 2.0)]
    out = fred.first_releases(rows, "level")
    assert [(r.actual, r.previous) for r in out] == [(1.0, None), (2.0, 1.0)]


def test_missing_key_without_cache_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(fred, "CACHE", tmp_path)
    monkeypatch.setattr(fred, "load_env", lambda: None)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FRED_API_KEY is not set and there is no cached copy of PAYEMS"):
        fred.fetch_vintages("PAYEMS")


def test_offline_reads_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(fred, "CACHE", tmp_path)
    (tmp_path / "PAYEMS.json").write_text(json.dumps(_rows()))

    def boom(*a, **k):
        raise AssertionError("network used")

    monkeypatch.setattr(httpx, "get", boom)
    assert fred.fetch_vintages("PAYEMS", offline=True) == _rows()


def test_fetch_paginates_skips_missing_and_caches(monkeypatch, tmp_path):
    monkeypatch.setattr(fred, "CACHE", tmp_path)
    monkeypatch.setattr(fred, "load_env", lambda: None)
    monkeypatch.setenv("FRED_API_KEY", "k")
    pages = {0: [_row("2024-01-01", "2024-02-01", 1), _row("2024-02-01", "2024-03-01", ".")],
             2: [_row("2024-03-01", "2024-04-01", 3)]}
    calls = []

    class Resp:
        def __init__(self, d): self.d = d
        def raise_for_status(self): pass
        def json(self): return self.d

    def fake_get(url, params=None, timeout=None):
        calls.append(params["offset"])
        return Resp({"count": 3, "observations": pages[params["offset"]]})

    monkeypatch.setattr(httpx, "get", fake_get)
    rows = fred.fetch_vintages("X")
    assert calls == [0, 2]
    assert [r["date"] for r in rows] == ["2024-01-01", "2024-03-01"]
    # fresh cache: second call makes no request
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("net")))
    assert fred.fetch_vintages("X") == rows
