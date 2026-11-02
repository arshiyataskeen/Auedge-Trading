"""Every INTEL_* flag, when ON, turns a qualifying BUY NOW plan into WAIT; when OFF the plan is unchanged."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import agents.chief as ch
from core.intel import entry as entry_m, news_extra, sessions, structure_q, volatility
from core.intel.sessions import SessionNow
from core.intel.volatility import StopCheck, VolResult
from core.liquidity import Pool
from core.models import AgentResult, Candle, CandleSet, MarketContext, SpotQuote

FLAGS = ("ALIGN", "SWEEP_BOS", "SESSION", "VOL", "ENTRY", "NEWS_EXTRA", "SCORE_GATE")


def _cs(tf):
    cs = [Candle(t=1_700_000_000 + i * 900, o=2000 + i * 0.1, h=2001 + i * 0.1, l=1999 + i * 0.1, c=2000.5 + i * 0.1, v=1)
          for i in range(100)]
    return CandleSet(key=f"fut_{tf}", timeframe=tf, kind="futures", source_label="t", candles=cs)


def _ctx():
    now = datetime(2026, 10, 14, 14, 0, tzinfo=timezone.utc)
    return MarketContext(generated_at=now, analysis_tf="15m",
                         spot=SpotQuote(price=2010.0, updated_at=now, age_seconds=1, stale=False, price_source="t"),
                         candles={f"fut_{t}": _cs(t) for t in ("1d", "4h", "1h", "15m", "5m")})


@pytest.fixture
def setup(monkeypatch):
    for f in FLAGS:
        monkeypatch.setenv(f"INTEL_{f}", "off")
    monkeypatch.setattr(ch, "tf_bias", lambda c, m: {"score": 2.5, "bias": "BUY", "bos": (99, "UP", 2005.0),
                                                      "recent_bos": True})
    monkeypatch.setattr(ch, "describe", lambda ctx, info: "t")
    pools = {"above": [Pool(price=2040.0, side="buy", strength=3, sources=["x"])],
             "below": [Pool(price=1990.0, side="sell", strength=3, sources=["x"])]}
    monkeypatch.setattr(ch, "build_stop_map", lambda ctx: {**pools, "recent_hunt": None, "atr1h": 5.0, "price": 2010.0})
    state = {"align": "aligned_up"}

    def _intel(ctx, rep):
        rep.intel = {"align": {"state": state["align"], "text": "t"}}
    monkeypatch.setattr(ch, "_intel", _intel)
    # factor sources: a clean setup by default
    monkeypatch.setattr(structure_q, "analyze", lambda c, s, n=8: structure_q.StructureQ(ok=True, text="ok"))
    monkeypatch.setattr(sessions, "current_sessions",
                        lambda t: SessionNow(sessions=["London"], low_liquidity=False, text="London"))
    monkeypatch.setattr(volatility, "regime", lambda c, p=None: VolResult("normal", "flat", 1, .001, 0, 9, "normal"))
    monkeypatch.setattr(volatility, "stop_check", lambda plan, c, p=None: StopCheck(True, 5, 9, "ok"))
    monkeypatch.setattr(news_extra, "extra_blackout", lambda ts, events=None: None)
    monkeypatch.setattr(entry_m, "check_entry",
                        lambda plan, c, pools: entry_m.EntryResult(False, True, True, True, text="ok"))
    return state


def _run():
    res = [AgentResult(agent="a", bias="BUY", confidence=80)]
    return ch.chief(_ctx(), res, {"a": 1.0}, AgentResult(agent="data_check", status="OK"))


def _with_flag(monkeypatch, name, on):
    monkeypatch.setenv(f"INTEL_{name}", "on" if on else "off")
    return _run()


def _break(name, monkeypatch, setup):
    if name == "ALIGN":
        setup["align"] = "aligned_down"
    elif name == "SWEEP_BOS":
        monkeypatch.setattr(structure_q, "analyze", lambda c, s, n=8: structure_q.StructureQ(ok=False, text="no"))
        import core.newsintel.m5 as m5
        monkeypatch.setattr(m5, "m5_confirmations", lambda c: {"retest": "none", "text": "no"})
    elif name == "SESSION":     # low liquidity AND a weak overall score (the flag only bites below 70)
        monkeypatch.setattr(sessions, "current_sessions",
                            lambda t: SessionNow(sessions=[], low_liquidity=True, text="Quiet hours"))
        _weak(monkeypatch, setup)
    elif name == "VOL":
        monkeypatch.setattr(volatility, "regime",
                            lambda c, p=None: VolResult("abnormal", "expanding", 9, .01, 1, 9, "Wild volatility"))
    elif name == "ENTRY":
        monkeypatch.setattr(entry_m, "check_entry",
                            lambda plan, c, pools: entry_m.EntryResult(True, False, True, False, text="Late entry"))
    elif name == "NEWS_EXTRA":
        monkeypatch.setattr(news_extra, "extra_blackout", lambda ts, events=None: {"name": "Fed speech"})
    elif name == "SCORE_GATE":
        _weak(monkeypatch, setup)


def _weak(monkeypatch, setup):
    setup["align"] = "aligned_down"
    monkeypatch.setattr(structure_q, "analyze", lambda c, s, n=8: structure_q.StructureQ(ok=False, text="no"))
    monkeypatch.setattr(entry_m, "check_entry",
                        lambda plan, c, pools: entry_m.EntryResult(True, False, False, False, text="bad"))
    import core.newsintel.m5 as m5
    monkeypatch.setattr(m5, "m5_confirmations", lambda c: {"retest": "none", "text": "no"})


def test_baseline_is_a_now_plan(setup):
    r = _run()
    assert r.plan.kind == "now" and r.bias == "BUY"


@pytest.mark.parametrize("name", FLAGS)
def test_flag_on_blocks_off_leaves(name, monkeypatch, setup):
    _break(name, monkeypatch, setup)
    off = _with_flag(monkeypatch, name, False)
    assert off.plan.kind == "now" and off.bias == "BUY", f"{name} off must not change the plan"
    on = _with_flag(monkeypatch, name, True)
    assert on.bias == "WAIT" and on.plan.kind != "now", f"{name} on must turn the plan into WAIT"
