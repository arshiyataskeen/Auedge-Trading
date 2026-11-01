"""Backtest: replays history in 15-minute steps and scores the Chief's trade plans.

Run:  .venv\\Scripts\\python.exe backtest.py          (options: --help)

How it works (no look-ahead):
- At each 15m bar close T it rebuilds a MarketContext from ONLY the candles finished by T. The 1H, 4H and
  Daily candles that are still open at T are built from the 15m bars seen so far, like the live dashboard
  sees a forming candle.
- It runs the 6 agents (stage 1, then the Skeptic), the data check and the Chief, exactly as app.py does.
- "BUY/SELL NOW" plans are entered at the next bar's open. "WAIT, then BUY/SELL" plans are entered only if
  price later trades through the entry and a 15m candle closes back (the plan's own rule) within 8 hours.
- One trade at a time. Exit at the stop or target 1 (a candle touching both counts as the stop); after 24h
  the trade is closed at the candle close. A spread/slippage cost is paid on entry and on exit.
All prices are gold FUTURES (Yahoo GC=F via XAUS), so futures_gap = 0. Analysis only: places no trades.
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import time
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from agents import BUILT_IN, DATA_CHECK
from agents import news_intel as _news_intel
from agents.base import run_agent
from agents.chief import chief, today_view
from core.snapshot import snap
from agents.psychology import (CHASE_ATR, COOLDOWN_AFTER_LOSS_S, FRIDAY_CUTOFF_NY, MAX_LOSSES_PER_DAY,
                               MAX_TRADES_PER_DAY)
from core import cot, news, votes, weights as aw
from core.data import API, aggregate
from core.indicators import atr
from core.models import Candle, CandleSet, MarketContext, SpotQuote
from core.track import HORIZON_S, MOVE_MIN

_news_intel.ALLOW_FETCH = False   # replays never download (FRED): offline and reproducible

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "backtest_cache"
REPORT = ROOT / "data" / "backtest_report.html"
NY = ZoneInfo("America/New_York")
LDN = ZoneInfo("Europe/London")
CACHE_MAX_AGE_S = 6 * 3600
PENDING_WINDOW_S = 8 * 3600
TRADE_EXPIRY_S = 24 * 3600
LABEL = "Gold FUTURES (COMEX GC=F) · Yahoo Finance via XAUS · backtest"

# What to download. 1H is fetched for 6 months so the live 3-month 1H window is full from the first step.
SERIES = {
    "fut_15m": "/chart?symbol=xau&interval=15m&range=1mo",
    "fut_1h": "/chart?symbol=xau&interval=1h&range=6mo",
    "fut_1d": "/chart?symbol=xau&interval=1d&range=2y",
    "dxy_1h": "/chart?symbol=dxy&interval=1h&range=6mo",
    "silver_1h": "/chart?symbol=silver&interval=1h&range=6mo",
    "sp500_1d": "/chart?symbol=sp500&interval=1d&range=1y",
}
# How much history the live dashboard gives the agents (see core/data.py), in seconds.
WINDOW = {"15m": 5 * 86400, "1h": 92 * 86400, "1d": 731 * 86400, "spot15": 48 * 3600,
          "dxy_1h": 31 * 86400, "silver_1h": 31 * 86400, "sp500_1d": 92 * 86400}


# ---------------------------------------------------------------- data
def _to_candles(points: list[dict]) -> list[Candle]:
    return [Candle(t=int(p["t"]), o=p["o"], h=p["h"], l=p["l"], c=p["c"], v=p.get("v") or 0)
            for p in points if None not in (p.get("o"), p.get("h"), p.get("l"), p.get("c"))]


def load_data(refresh: bool, offline: bool) -> dict[str, list[Candle]]:
    """Download each series (or reuse the cache). New downloads are MERGED with the cache, so the 15m history
    keeps growing every time you run this (XAUS only serves about 1 month of 15m candles at a time)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    out = {}
    with httpx.Client(timeout=30) as client:
        for name, path in SERIES.items():
            f = CACHE / f"{name}.json"
            old = json.loads(f.read_text()) if f.exists() else {"fetched_at": 0, "points": []}
            fresh = time.time() - old["fetched_at"] < CACHE_MAX_AGE_S
            if not offline and (refresh or not fresh):
                try:
                    r = client.get(API + path)
                    r.raise_for_status()
                    new = r.json().get("points", [])
                    merged = {p["t"]: p for p in old["points"]}
                    merged.update({p["t"]: p for p in new})
                    old = {"fetched_at": time.time(), "points": [merged[t] for t in sorted(merged)]}
                    tmp = f.with_suffix(".tmp")
                    tmp.write_text(json.dumps(old))
                    tmp.replace(f)                     # atomic: a backtest reading the file never sees half of it
                    print(f"  downloaded {name}: {len(new)} candles")
                except Exception as e:  # noqa: BLE001 - fall back to whatever is cached
                    if not old["points"]:
                        raise SystemExit(f"Could not download {name} ({e}) and there is no cached copy.")
                    print(f"  {name}: download failed ({e}); using the cached copy")
            else:
                print(f"  {name}: using cached copy ({len(old['points'])} candles)")
            # Drop intraday candles that were still forming when downloaded (their high/low/close are not final).
            sec = {"15m": 900, "1h": 3600}.get(name.rsplit("_", 1)[1])
            out[name] = [c for c in _to_candles(old["points"]) if not sec or c.t + sec <= old["fetched_at"]]
    return out


def session_day(t: int) -> str:
    """Trading day a timestamp belongs to. Gold's day runs 18:00-17:00 New York time, named after its end
    (the same day Yahoo stamps on its daily candle at 00:00 New York)."""
    return (datetime.fromtimestamp(t, NY) + timedelta(hours=6)).strftime("%Y-%m-%d")


def merge(bars: list[Candle], sec: int | None = None) -> Candle | None:
    """One candle from consecutive bars (time = bucket start if `sec` is given, else first bar's time)."""
    if not bars:
        return None
    t = bars[0].t // sec * sec if sec else bars[0].t
    return Candle(t=t, o=bars[0].o, h=max(b.h for b in bars), l=min(b.l for b in bars), c=bars[-1].c,
                  v=sum(b.v for b in bars))


class History:
    """All downloaded candles, with fast 'what was known at time T' lookups."""

    def __init__(self, raw: dict[str, list[Candle]]):
        self.m15 = raw["fut_15m"]
        self.h1 = raw["fut_1h"]
        self.h4 = aggregate([c.model_dump() for c in self.h1], 14400)
        self.d1 = raw["fut_1d"]
        self.d1_day = [datetime.fromtimestamp(c.t, NY).strftime("%Y-%m-%d") for c in self.d1]
        self.m15_day = [session_day(c.t) for c in self.m15]
        self.h1_day = [session_day(c.t) for c in self.h1]
        self.markets = {k: raw[k] for k in ("dxy_1h", "silver_1h", "sp500_1d")}
        self.cot = cot.load_sync()          # weekly; cot.view() only uses reports published by T
        self.t15 = [c.t for c in self.m15]
        self.t1h = [c.t for c in self.h1]
        self.t4h = [c.t for c in self.h4]
        self.tm = {k: [c.t for c in v] for k, v in self.markets.items()}

    def context(self, i: int) -> MarketContext:
        """MarketContext at the close of 15m bar i (T = its start + 15 min), from closed candles only."""
        T = self.m15[i].t + 900
        now = datetime.fromtimestamp(T, timezone.utc)
        ctx = MarketContext(generated_at=now, analysis_tf="15m", futures_gap=0.0,
                            futures_last=self.m15[i].c, futures_last_age_s=0)
        m15 = self.m15[bisect_left(self.t15, T - WINDOW["15m"]):i + 1]

        # 1H: finished 1H candles + the current hour built from its 15m bars
        hour0 = T // 3600 * 3600 if T % 3600 else T          # start of the hour still forming at T
        h1 = self.h1[bisect_left(self.t1h, T - WINDOW["1h"]):bisect_left(self.t1h, hour0)]
        forming_h = merge([c for c in m15[-4:] if c.t >= hour0])
        if forming_h:
            forming_h.t = hour0
            h1 = h1 + [forming_h]
        # 4H: finished 4H buckets + the current bucket built from its 1H candles (as core/data.py does)
        b4 = T // 14400 * 14400 if T % 14400 else T
        h4 = self.h4[bisect_left(self.t4h, T - WINDOW["1h"]):bisect_left(self.t4h, b4)]
        forming_4 = merge([c for c in h1[-4:] if c.t >= b4], 14400)
        if forming_4:
            h4 = h4 + [forming_4]
        # Daily: finished days + today built from today's 15m bars
        today = self.m15_day[i]
        d1 = [c for c, d in zip(self.d1, self.d1_day) if d < today and c.t >= T - WINDOW["1d"]]
        j = i
        while j > 0 and self.m15_day[j - 1] == today:
            j -= 1
        forming_d = merge(self.m15[j:i + 1])
        if forming_d:
            d1 = d1 + [forming_d]

        for key, tf, cl in (("fut_15m", "15m", m15), ("fut_1h", "1h", h1), ("fut_4h", "4h", h4), ("fut_1d", "1d", d1)):
            ctx.candles[key] = CandleSet(key=key, timeframe=tf, kind="futures", source_label=LABEL, candles=cl,
                                         last_is_forming=tf != "15m")
        # The live data check measures volatility on 48h of spot 15m candles; here futures stand in for spot.
        ctx.candles["spot_15m"] = CandleSet(key="spot_15m", timeframe="15m", kind="spot", source_label=LABEL,
                                            candles=self.m15[bisect_left(self.t15, T - WINDOW["spot15"]):i + 1],
                                            last_is_forming=False)
        for k, cl in self.markets.items():
            sec = 86400 if k.endswith("1d") else 3600
            end = bisect_left(self.tm[k], T - sec + 1)        # only candles finished by T
            ctx.markets[k] = cl[bisect_left(self.tm[k], T - WINDOW[k]):end]
        ctx.cot = self.cot
        ctx.spot = SpotQuote(price=self.m15[i].c, updated_at=now, age_seconds=0, stale=False,
                             price_source="backtest (futures 15m close)")
        return ctx


# ---------------------------------------------------------------- one analysis step
BASE_WEIGHTS = {a.name: (a.weight if a.votes else 0) for a in BUILT_IN}


_AGENT_CACHE: dict = {}        # health check: agent results per step, reused by every variant (only the Chief re-runs)


HTF_SIDE: dict = {"side": None}      # the Wyckoff + Elliott side at the current step (for the f_htf filters)


from core.dataset import htf_side  # noqa: E402 - Wyckoff + Elliott side: BUY, SELL or RANGE


async def analyse(ctx: MarketContext, weights: dict | None = None):
    key = (SETTINGS.get("cache_ns"), ctx.generated_at.timestamp())
    if SETTINGS.get("cache") and key in _AGENT_CACHE:
        results, check = _AGENT_CACHE[key]
    else:
        stage1 = [a for a in BUILT_IN if getattr(a, "stage", 1) == 1]
        stage2 = [a for a in BUILT_IN if getattr(a, "stage", 1) == 2]
        results = list(await asyncio.gather(*(run_agent(a, ctx) for a in stage1)))
        ctx.prior = results
        results += await asyncio.gather(*(run_agent(a, ctx) for a in stage2))
        check = await run_agent(DATA_CHECK, ctx)
        if SETTINGS.get("cache"):
            _AGENT_CACHE[key] = (results, check)
    HTF_SIDE["side"] = htf_side(results)
    w = dict(weights or BASE_WEIGHTS)
    drop = SETTINGS.get("drop") or []
    off = set([drop] if isinstance(drop, str) else drop)          # health check: these votes are left out
    if SETTINGS.get("live_votes", True):
        off |= set(votes.off())                                   # the same votes as live (review board / you)
    off -= set(SETTINGS.get("add") or [])                          # review board: test switching a vote back on
    for name in off:
        w[name] = 0
    rep = chief(ctx, results, w, check)
    rep.today = today_view(rep)
    if SETTINGS.get("record"):          # tools/build_dataset.py: keep every replayed step for training
        from core import dataset
        dataset.record_step(SETTINGS["record"]["src"], SETTINGS["record"]["run"], ctx.generated_at.timestamp(), ctx.futures_last,
                            results, rep, buffered=True)
    return results, rep


class WalkForward:
    """Weekly performance weights inside a replay (core/weights.py rules). At the start of each trading week it scores
    the calls whose 4-hour outcome was already known by then (no look-ahead) and sets new multipliers."""

    def __init__(self, ends: list[int], closes: list[float]):
        self.ends, self.closes = ends, closes
        self.scored, self.i, self.week, self.mult, self.history = [], 0, None, {}, []

    def weights(self, T: int, calls: list[dict]) -> dict:
        if not SETTINGS.get("adaptive", True):
            return BASE_WEIGHTS
        wk = aw.week_start(T)
        if wk != self.week:
            while self.i < len(calls) and calls[self.i]["t"] + HORIZON_S <= wk:
                c = calls[self.i]
                j = bisect_left(self.ends, c["t"] + HORIZON_S)          # candle ending 4 hours after the call
                if j < len(self.ends) and self.ends[j] <= wk:
                    if c["agent"] != "chief":
                        move = (self.closes[j] - c["price"]) * (1 if c["bias"] == "BUY" else -1)
                        self.scored.append((c["agent"], c["t"],
                                            "hit" if move >= MOVE_MIN else "miss" if move <= -MOVE_MIN else "flat"))
                self.i += 1
            self.week, self.mult = wk, aw.multipliers(self.scored, wk)
            self.history.append({"week": wk, "mult": {k: v["mult"] for k, v in self.mult.items() if v["mult"] != 1.0}})
        return aw.apply(BASE_WEIGHTS, self.mult)


# ---------------------------------------------------------------- trade simulation
# Trade settings (set by main()/web_run()): fixed reward:risk target instead of the plan's target, and whether
# half the position comes off at 1R. Dollar results use a fixed lot: 1 lot = 100 oz, so 0.1 lot = $10 per $1 move.
SETTINGS = {"target_rr": None, "partial": True, "account": 25000.0, "lot": 0.1, "news": True, "adaptive": False,
            "day_max_loss": 350.0, "day_max_profit": 150.0,      # per trading day, in dollars at the fixed lot; 0 = off
            "live_rules": True,      # the live Discipline coach's other rules: 2 losses a day, 60-min cool-down, no chasing
            "stop_slip": 0.0,        # extra dollars lost when a stop / breakeven order fills (cost stress test)
            "f_session": False,      # quality filter: only 07:00 London to 12:00 New York (the busiest hours)
            "f_trend": False, "f_htf": False, "f_htf_strict": False,
            "runner_rr": None, "trail_r": None, "min_conf": None,        # quality filter: only when the Daily and 4H both point the trade's way
            "f_hunt": False,         # quality filter: only right after a stop hunt against the trade's side
            "drop": None, "cache": False}   # health check internals


def exit_on_bar(tr: dict, c: Candle, spread: float, sec: int = 900) -> bool:
    """Check one candle against an open trade; fill exit fields and return True if it closed.
    Half the position comes off at 1R ("be") and the stop of the other half moves to the entry price."""
    s, t1, be = tr["s"], tr["t1"], tr["be"]
    half = tr.get("half_r")
    stop = tr["entry"] if half is not None else tr["stop"]
    stop_name = "breakeven" if half is not None else "stop"
    trail = SETTINGS.get("trail_r")
    if half is not None and trail and tr.get("best") is not None:     # runner: stop follows the best FINISHED price
        tstop = tr["best"] - s * trail * tr["risk"]
        if (tstop - stop) * s > 0:
            stop, stop_name = round(tstop, 2), "trailing stop"
    px = why = None
    if (c.o - stop) * s <= 0:
        px, why = c.o, f"{stop_name} (gap)"
    elif (c.o - t1) * s >= 0:
        px, why = c.o, "target (gap)"
    elif (c.l <= stop) if s > 0 else (c.h >= stop):
        px, why = stop, stop_name                         # stop first if one candle touches both
    else:
        if half is None and be is not None and ((c.h >= be) if s > 0 else (c.l <= be)):
            hp = c.o if (c.o - be) * s > 0 else be         # opened beyond 1R: take half at the open
            half = tr["half_r"] = round((hp - s * spread - tr["entry"]) * s / tr["risk"], 2)
            run_rr = SETTINGS.get("runner_rr")
            if run_rr:                                     # the runner aims further than the plan's target
                t1 = tr["t1"] = round(tr["entry"] + s * max(run_rr * tr["risk"], abs(t1 - tr["entry"])), 2)
        if (c.h >= t1) if s > 0 else (c.l <= t1):
            px, why = t1, "target"
        elif c.t + sec >= tr["entry_t"] + TRADE_EXPIRY_S:
            px, why = c.c, "expired (24h)"
    if px is None:
        if half is not None:                               # remember the best price so far for the trailing stop
            ext = c.h if s > 0 else c.l
            tr["best"] = ext if tr.get("best") is None else (max if s > 0 else min)(tr["best"], ext)
        return False
    slip = SETTINGS.get("stop_slip", 0.0) if why.startswith(("stop", "breakeven", "trailing")) else 0.0
    fill = px - s * (spread + slip)
    rest = (fill - tr["entry"]) * s / tr["risk"]
    r = 0.5 * half + 0.5 * rest if half is not None else rest
    tr.update(exit_t=c.t + sec, exit=round(fill, 2), why=why + (" after half at 1R" if half is not None else ""),
              r=round(r, 2))
    return True


def open_trade(plan, kind: str, t: int, price: float, spread: float, decided_t: int) -> dict | None:
    s = 1 if plan.side == "BUY" else -1
    fill = price + s * spread
    if (fill - plan.stop) * s <= 0 or (fill - plan.t1) * s >= 0:
        return None                                        # the plan's own "do not enter if..." rule
    risk = abs(fill - plan.stop)
    t1 = round(fill + s * SETTINGS["target_rr"] * risk, 2) if SETTINGS["target_rr"] else plan.t1
    return {"side": plan.side, "s": s, "kind": kind, "decided_t": decided_t, "entry_t": t, "entry": round(fill, 2),
            "stop": plan.stop, "t1": t1, "be": round(fill + s * risk, 2) if SETTINGS["partial"] else None, "risk": risk}


def add_dollars(trades: list[dict]) -> dict:
    """Dollar P&L at the fixed lot (costs already in the fills) and the account path from SETTINGS['account']."""
    oz = 100 * SETTINGS["lot"]
    bal = peak = SETTINGS["account"]
    dd = 0.0
    for t in trades:
        t["usd"] = round(t["r"] * t["risk"] * oz, 2)
        bal += t["usd"]
        peak = max(peak, bal)
        dd = max(dd, peak - bal)
        t["balance"] = round(bal, 2)
    total = round(bal - SETTINGS["account"], 2)
    return {"account": SETTINGS["account"], "lot": SETTINGS["lot"], "total_usd": total, "end_balance": round(bal, 2),
            "return_pct": round(100 * total / SETTINGS["account"], 2), "max_dd_usd": round(dd, 2),
            "avg_usd": round(total / len(trades), 2) if trades else None,
            "best_usd": max((t["usd"] for t in trades), default=None), "worst_usd": min((t["usd"] for t in trades), default=None),
            "avg_risk_usd": round(sum(t["risk"] for t in trades) / len(trades) * oz, 2) if trades else None}


def book(day_pnl: dict, trade: dict, live: dict | None = None) -> None:
    """Add a closed trade's dollar result (fixed lot) to its trading day, for the daily loss / profit limits,
    and count losing trades for the live rules (2 losses a day, cool-down)."""
    k = session_day(trade["exit_t"] - 1)
    day_pnl[k] = day_pnl.get(k, 0.0) + trade["r"] * trade["risk"] * 100 * SETTINGS["lot"]
    if live is not None and trade["r"] < 0:
        live["losses"][k] = live["losses"].get(k, 0) + 1
        live["last_loss"] = trade["exit_t"]


def chasing(ctx: MarketContext) -> bool:
    """Same as the Discipline coach: price ran more than 1.5x the 1H ATR in the last hour."""
    m15, h1 = ctx.struct("15m"), ctx.struct("1h")
    if not m15 or not h1 or len(m15.candles) < 5 or len(h1.candles) < 20:
        return False
    a1 = atr(h1.candles)[-1] or 0
    return bool(a1) and abs(m15.candles[-1].c - m15.candles[-5].c) > CHASE_ATR * a1


def main_session(T: int) -> bool:
    """07:00 London to 12:00 New York: London open through the London / New York overlap."""
    return datetime.fromtimestamp(T, LDN).hour >= 7 and datetime.fromtimestamp(T, NY).hour < 12


def quality_block(T: int, rep) -> str | None:
    """Optional setup-quality filters (Backtest tab / health check)."""
    side = rep.plan.side
    if SETTINGS.get("f_session") and not main_session(T):
        return "f_session"
    if SETTINGS.get("f_trend") and not all(side in t.bias for t in rep.timeframes if t.tf in ("Daily", "4H")):
        return "f_trend"
    if SETTINGS.get("min_conf") and rep.confidence < SETTINGS["min_conf"]:
        return "min_conf"             # weak agreement: the Chief's confidence is under the threshold
    hs = HTF_SIDE["side"]
    if SETTINGS.get("f_htf") and hs in ("BUY", "SELL") and side != hs:
        return "f_htf"                # against the Wyckoff + Elliott side
    if SETTINGS.get("f_htf_strict") and side != hs:
        return "f_htf"                # strict: also no trades when they call a range
    h = rep.recent_hunt
    if SETTINGS.get("f_hunt") and not (h and h.side == ("sell" if side == "BUY" else "buy")):
        return "f_hunt"
    return None


def block_reason(T: int, opened: dict, day_pnl: dict | None = None, risk_usd: float = 0.0, live: dict | None = None,
                 ctx: MarketContext | None = None, rep=None) -> str | None:
    """Why a new trade may not open at T (same rules as the live Discipline coach), or None: Friday afternoon
    (New York), the daily trade cap, the daily dollar loss limit / profit target, or a high-impact news window."""
    ny = datetime.fromtimestamp(T, NY)
    if ny.weekday() == 4 and ny.hour >= FRIDAY_CUTOFF_NY:
        return "friday"
    if opened.get(session_day(T), 0) >= MAX_TRADES_PER_DAY:
        return "daily_cap"
    pnl = (day_pnl or {}).get(session_day(T), 0.0)
    if SETTINGS.get("day_max_loss") and pnl <= -SETTINGS["day_max_loss"]:
        return "day_loss_limit"
    if SETTINGS.get("day_max_loss") and pnl - risk_usd < -SETTINGS["day_max_loss"]:
        return "day_loss_room"          # if this trade's stop is hit, the day would end beyond the loss limit
    if SETTINGS.get("day_max_profit") and pnl >= SETTINGS["day_max_profit"]:
        return "day_profit_target"
    if SETTINGS.get("news", True) and news.blackout(T):
        return "news"
    if live is not None and SETTINGS.get("live_rules", True):
        if live["losses"].get(session_day(T), 0) >= MAX_LOSSES_PER_DAY:
            return "two_losses"
        if T - live["last_loss"] < COOLDOWN_AFTER_LOSS_S:
            return "cooldown"
        if ctx is not None and chasing(ctx):
            return "chase"
    return quality_block(T, rep) if rep is not None else None


async def run(hist: History, spread: float, days: float | None, start_t: int | None = None, end_t: int | None = None,
              progress=None) -> tuple[list[dict], list[dict], dict]:
    m15 = hist.m15
    # First step: once the live 5-day 15m window is full (and >= 60 bars).
    first = max(bisect_left(hist.t15, m15[0].t + WINDOW["15m"]), 60)
    if days:
        first = max(first, bisect_left(hist.t15, m15[-1].t - days * 86400))
    if start_t:
        first = max(first, bisect_left(hist.t15, start_t - 900))
    last = min(len(m15), bisect_left(hist.t15, end_t)) if end_t else len(m15)
    if last <= first:
        raise ValueError("No 15m candles in that period (15-minute history covers only about the last month).")
    trades, calls, steps = [], [], []
    pending, trade, opened, day_pnl, live = None, None, {}, {}, {"losses": {}, "last_loss": 0}
    wf = WalkForward([c.t + 900 for c in m15], [c.c for c in m15])
    counts = {"steps": 0, "now": 0, "pending": 0, "none": 0, "veto": 0,
              "pending_cancelled": 0, "pending_expired": 0, "skipped_entry": 0}
    started = time.time()
    n = last - first
    for i in range(first, last):
        c = m15[i]
        # 1) Bar i happened: manage the open trade / the waiting order with it.
        if trade and trade["entry_t"] <= c.t and exit_on_bar(trade, c, spread):
            trades.append(trade)
            book(day_pnl, trade, live)
            trade = None
        if pending and not trade:
            p, s = pending["plan"], pending["s"]
            lvl = p.entry_hi if s > 0 else p.entry_lo        # the stop pool's price
            if (c.c - p.stop) * s < 0:
                pending, counts["pending_cancelled"] = None, counts["pending_cancelled"] + 1
            else:
                if (c.l < lvl) if s > 0 else (c.h > lvl):
                    pending["pierced"] = True
                if pending["pierced"] and (c.c - lvl) * s > 0:
                    trade = open_trade(p, "pending", c.t + 900, c.c, spread, pending["decided_t"])
                    if trade:
                        trade["conf"] = pending["conf"]
                    counts["skipped_entry"] += trade is None
                    pending = None
                elif c.t + 900 - pending["decided_t"] >= PENDING_WINDOW_S:
                    pending, counts["pending_expired"] = None, counts["pending_expired"] + 1

        # 2) Analysis at the close of bar i (no future candles in ctx).
        ctx = hist.context(i)
        results, rep = await analyse(ctx, wf.weights(c.t + 900, calls))
        steps.append(snap(c.t + 900, c.c, results, rep))          # for the Calendar tab
        counts["steps"] += 1
        counts[rep.plan.kind] = counts.get(rep.plan.kind, 0) + 1
        counts["veto"] += rep.headline.startswith("NO TRADE: data check")
        T = c.t + 900
        direction = "BUY" if rep.weighted_score >= 0.15 else "SELL" if rep.weighted_score <= -0.15 else None
        for r in results:
            if r.status == "OK" and r.bias in ("BUY", "SELL"):
                calls.append({"agent": r.agent, "bias": r.bias, "t": T, "price": c.c, "i": i})
        if direction:
            calls.append({"agent": "chief", "bias": direction, "t": T, "price": c.c, "i": i})

        # 3) Act on the plan (only when not already in a trade).
        if not trade:
            plan = rep.plan
            if pending and (direction != pending["plan"].side):
                pending, counts["pending_cancelled"] = None, counts["pending_cancelled"] + 1   # bias changed
            why_block = (block_reason(T, opened, day_pnl, abs((plan.entry_lo + plan.entry_hi) / 2 - plan.stop) * 100 * SETTINGS["lot"],
                                      live, ctx, rep)
                         if plan.kind == "now" and plan.stop and plan.t1 else None)
            if why_block:
                counts["blocked_" + why_block] = counts.get("blocked_" + why_block, 0) + 1
            elif plan.kind == "now" and plan.stop and plan.t1 and i + 1 < len(m15):
                pending = None
                trade = open_trade(plan, "now", m15[i + 1].t, m15[i + 1].o, spread, T)
                if trade:
                    trade["conf"] = rep.confidence
                    opened[session_day(T)] = opened.get(session_day(T), 0) + 1
                counts["skipped_entry"] += trade is None
            elif plan.kind == "pending" and plan.stop and plan.t1 and not pending:
                pending = {"plan": plan, "s": 1 if plan.side == "BUY" else -1, "decided_t": T, "pierced": False,
                           "conf": rep.confidence}

        done = i - first + 1
        if progress and (done % 25 == 0 or done == n):
            progress(done, n)
        if done % 100 == 0 or done == n:
            el = time.time() - started
            print(f"\r  step {done}/{n}  ({el:.0f}s, about {el / done * (n - done):.0f}s left)   ", end="", flush=True)
    print()
    counts["open_at_end"] = 1 if trade else 0
    counts["first_t"], counts["last_t"] = m15[first].t + 900, m15[last - 1].t + 900
    counts["_steps"] = steps
    counts["weights_history"] = wf.history
    return trades, calls, counts


# ---------------------------------------------------------------- scoring
def score_calls(hist: History, calls: list[dict]) -> dict:
    """Same rule as core/track.py: compare with the close of the candle ending 4 hours later."""
    out: dict[str, dict] = {}
    for x in calls:
        j = bisect_left(hist.t15, x["t"] + HORIZON_S - 900)
        a = out.setdefault(x["agent"], {"calls": 0, "hits": 0, "misses": 0, "flat": 0, "unscored": 0})
        a["calls"] += 1
        if j >= len(hist.m15):
            a["unscored"] += 1
            continue
        move = (hist.m15[j].c - x["price"]) * (1 if x["bias"] == "BUY" else -1)
        a["hits" if move >= MOVE_MIN else "misses" if move <= -MOVE_MIN else "flat"] += 1
    for a in out.values():
        d = a["hits"] + a["misses"]
        a["hit_rate"] = round(100 * a["hits"] / d) if d else None
    return out


def summarize(trades: list[dict]) -> dict:
    rs = [t["r"] for t in trades]
    eq, peak, dd, streak, worst = 0.0, 0.0, 0.0, 0, 0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        streak = streak + 1 if r < 0 else 0
        worst = max(worst, streak)
    wins = sum(r > 0 for r in rs)
    return {"n": len(rs), "wins": wins, "losses": sum(r < 0 for r in rs),
            "win_rate": round(100 * wins / len(rs)) if rs else None,
            "avg_r": round(sum(rs) / len(rs), 2) if rs else None, "total_r": round(sum(rs), 2),
            "max_dd": round(dd, 2), "streak": worst,
            "targets": sum(t["why"].startswith("target") for t in trades),
            "stops": sum(t["why"].startswith("stop") for t in trades),
            "breakeven": sum(t["why"].startswith("breakeven") for t in trades),
            "half_at_1r": sum("half at 1R" in t["why"] for t in trades),
            "expired": sum(t["why"].startswith("expired") for t in trades)}


AGENT_NAMES = {"wyckoff": "Wyckoff", "elliott": "Elliott", "smc": "Smart money", "price_action": "Price action",
               "trend": "Trend analyst", "sentiment": "Market psychology", "stophunt": "Stop-hunt", "ict": "ICT", "macro": "Session and macro", "skeptic": "Skeptic", "chief": "Chief (weighted timeframes)"}


def when(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%a %d %b %H:%M UTC")


def plain_summary(s: dict, groups: dict, agents: dict, counts: dict, spread: float) -> list[str]:
    days = (counts["last_t"] - counts["first_t"]) / 86400
    L = [f"Tested period: {when(counts['first_t'])} to {when(counts['last_t'])} (about {days:.0f} days, "
         f"{counts['steps']} analyses, one every 15 minutes).",
         f"Costs assumed: ${spread:.2f} spread/slippage on entry and again on exit."]
    if not s["n"]:
        L.append("The Chief's rules did not produce a single completed trade in this period, so there is nothing "
                 "to judge yet. Run it again in a few weeks: the downloaded history keeps growing.")
        return L
    L.append(f"The plans led to {s['n']} trades: {s['wins']} won and {s['losses']} lost (win rate {s['win_rate']}%).")
    L.append(f"Average result {s['avg_r']:+.2f}R per trade, total {s['total_r']:+.2f}R. "
             f"(1R = the amount you would lose if the stop is hit. Risking 1% per trade, "
             f"{s['total_r']:+.2f}R is roughly {s['total_r']:+.1f}% of the account.)")
    L.append(f"Worst drop from a high point: {s['max_dd']:.2f}R. Longest run of losers in a row: {s['streak']}.")
    verdict = ("made money in this test" if s["total_r"] > 0 else "lost money in this test" if s["total_r"] < 0
               else "broke even in this test")
    L.append(f"Overall the rules {verdict}. With only {s['n']} trades this is NOT enough to trust: "
             f"a handful of trades going the other way would change the picture.")
    for k, g in groups.items():
        if g["n"]:
            L.append(f"  {k}: {g['n']} trades, win rate {g['win_rate']}%, total {g['total_r']:+.2f}R")
    best = sorted(((a, v) for a, v in agents.items() if v["hit_rate"] is not None and v["hits"] + v["misses"] >= 20),
                  key=lambda x: -x[1]["hit_rate"])
    if best:
        L.append("4-hour direction calls (a coin flip would be about 50%): " +
                 ", ".join(f"{AGENT_NAMES.get(a, a)} {v['hit_rate']}%" for a, v in best) + ".")
    L.append("Past results do not guarantee future results.")
    return L


# ---------------------------------------------------------------- HTML report
def html_report(s, groups, agents, trades, counts, lines, spread) -> str:
    e = html.escape

    def num(v, fmt="{:+.2f}"):
        return "n/a" if v is None else fmt.format(v)

    def cls(v):
        return "" if v is None else "up" if v > 0 else "down" if v < 0 else ""

    stat_rows = [("Trades", s["n"], ""), ("Win rate", num(s["win_rate"], "{}%"), ""),
                 ("Average R per trade", num(s["avg_r"]), cls(s["avg_r"])),
                 ("Total R", num(s["total_r"]), cls(s["total_r"])),
                 ("Max drawdown", num(s["max_dd"], "{:.2f}R"), "down" if s["max_dd"] else ""),
                 ("Longest losing streak", s["streak"], ""),
                 ("Exits: target / stop / 24h expiry", f"{s['targets']} / {s['stops']} / {s['expired']}", "")]
    kpis = "".join(f'<div class="kpi"><div class="k">{e(k)}</div><div class="v {c}">{e(str(v))}</div></div>'
                   for k, v, c in stat_rows)
    grp = "".join(f"<tr><td>{e(k)}</td><td>{g['n']}</td><td>{num(g['win_rate'], '{}%')}</td>"
                  f"<td class='{cls(g['avg_r'])}'>{num(g['avg_r'])}</td><td class='{cls(g['total_r'])}'>{num(g['total_r'])}</td>"
                  f"<td>{num(g['max_dd'], '{:.2f}')}</td><td>{g['streak']}</td></tr>" for k, g in groups.items())
    ag = "".join(f"<tr><td>{e(AGENT_NAMES.get(a, a))}</td><td>{v['calls']}</td><td>{v['hits']}</td><td>{v['misses']}</td>"
                 f"<td>{v['flat']}</td><td><b>{num(v['hit_rate'], '{}%')}</b></td></tr>"
                 for a, v in sorted(agents.items(), key=lambda x: x[0] == "chief"))
    tr = "".join(f"<tr><td>{e(when(t['entry_t']))}</td><td class='{'up' if t['side'] == 'BUY' else 'down'}'>{t['side']}</td>"
                 f"<td>{'NOW' if t['kind'] == 'now' else 'WAIT then'}</td><td>{t['entry']:,.2f}</td><td>{t['stop']:,.2f}</td>"
                 f"<td>{t['t1']:,.2f}</td><td>{t['exit']:,.2f}</td><td>{e(t['why'])}</td>"
                 f"<td class='{cls(t['r'])}'>{t['r']:+.2f}</td></tr>" for t in reversed(trades))
    plans = (f"{counts['steps']} analyses: {counts.get('now', 0)} said BUY/SELL NOW, {counts.get('pending', 0)} said "
             f"WAIT then BUY/SELL, {counts.get('none', 0)} said no trade ({counts['veto']} of those because the market "
             f"was closed or volatility was extreme). Waiting orders cancelled: {counts['pending_cancelled']}, "
             f"expired after 8h: {counts['pending_expired']}. Entries skipped because price was already past the "
             f"stop or target: {counts['skipped_entry']}. Most analyses happen while a trade is already open, "
             f"and only one trade is held at a time."
             + (" One trade was still open when the data ended; it is not counted." if counts["open_at_end"] else ""))
    summary = "".join(f"<li>{e(x.strip())}</li>" for x in lines)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AuEdge Backtest</title>
<style>
  :root {{ --bg:#0f1115; --panel:#171a21; --line:#262b35; --text:#d6dae1; --muted:#8a92a0;
           --up:#26a69a; --down:#ef5350; --warn:#f0b429; --accent:#4c8dff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  main {{ max-width:1100px; margin:0 auto; padding:16px; }}
  h1 {{ font-size:20px; margin:0 0 4px; }} h2 {{ font-size:15px; margin:24px 0 8px; }}
  .meta {{ color:var(--muted); font-size:12px; }}
  .warn {{ background:rgba(240,180,41,.12); border:1px solid rgba(240,180,41,.35); color:var(--warn);
           padding:8px 12px; border-radius:8px; margin:12px 0; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px; }}
  .kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px; }}
  .kpi .k {{ color:var(--muted); font-size:12px; }} .kpi .v {{ font-size:20px; font-weight:700; font-variant-numeric:tabular-nums; }}
  ul {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px 10px 10px 28px; margin:0; }}
  .scroll {{ overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line);
           border-radius:8px; font-variant-numeric:tabular-nums; }}
  th, td {{ padding:6px 10px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }}
  th {{ color:var(--muted); font-weight:600; font-size:12px; }}
  .up {{ color:var(--up); }} .down {{ color:var(--down); }}
</style></head><body><main>
<h1>AuEdge backtest: XAUUSD trade plans</h1>
<div class="meta">{e(when(counts['first_t']))} to {e(when(counts['last_t']))} · gold futures 15m candles ·
cost ${spread:.2f} per side · made {e(datetime.now().strftime('%Y-%m-%d %H:%M'))}</div>
<div class="warn">Past results do not guarantee future results. This test covers only about a month and a small number
of trades, so luck plays a big part. Analysis only, not financial advice.</div>
<h2>In plain words</h2><ul>{summary}</ul>
<h2>Key numbers</h2><div class="kpis">{kpis}</div>
<p class="meta">R = profit or loss measured in "risk units": 1R is what you lose when the stop is hit.
+1.5R means you made 1.5 times what you risked. Drawdown = the worst drop from a previous high, in R.</p>
<h2>Split by side and plan type</h2>
<div class="scroll"><table><tr><th>Group</th><th>Trades</th><th>Win rate</th><th>Avg R</th><th>Total R</th><th>Max DD (R)</th><th>Losing streak</th></tr>{grp}</table></div>
<h2>How often each agent called the 4-hour direction right</h2>
<div class="scroll"><table><tr><th>Agent</th><th>BUY/SELL calls</th><th>Right (≥ $3 its way)</th><th>Wrong (≥ $3 against)</th><th>Flat</th><th>Hit rate</th></tr>{ag}</table></div>
<p class="meta">Same rule as the dashboard's live track record. Hit rate ignores flat moves; about 50% is no better
than a coin flip. Calls are made every 15 minutes, so neighbouring calls overlap and are not independent.</p>
<h2>What the Chief said</h2><p class="meta">{e(plans)}</p>
<h2>All trades (newest first)</h2>
<div class="scroll"><table><tr><th>Entered</th><th>Side</th><th>Plan</th><th>Entry</th><th>Stop</th><th>Target 1</th><th>Exit</th><th>How it ended</th><th>Result (R)</th></tr>
{tr or '<tr><td colspan="9">No trades.</td></tr>'}</table></div>
<p class="meta">Prices are COMEX gold futures (they run a few dollars above spot XAU/USD). Entry and exit include the
assumed cost.</p>
</main></body></html>"""


# ---------------------------------------------------------------- 1-hour mode (about 6 months)
# The free API only serves ~1 month of 15m candles, so a 6-month test steps once per closed 1H candle.
# Where real 15m candles cover the agents' 5-day "15m" window, they are used; before that, 1H candles sit in
# the "15m" slot ("approximated" period) and trades are managed on 1H candles. Results are split by period.
REPORT_6M = ROOT / "data" / "backtest_report_6m.html"
HOURLY_WARMUP_S = 30 * 86400        # first step once 30 days of 1H history exist (Chief needs 60+ 4H candles)


def context_hourly(hist: History, T: int, real15: bool) -> MarketContext:
    """MarketContext at the hour boundary T, from candles closed by T only."""
    now = datetime.fromtimestamp(T, timezone.utc)
    j1 = bisect_left(hist.t1h, T)                                   # 1H candles starting before T = all closed
    h1 = hist.h1[bisect_left(hist.t1h, T - WINDOW["1h"]):j1]
    b4 = T // 14400 * 14400
    h4 = hist.h4[bisect_left(hist.t4h, T - WINDOW["1h"]):bisect_left(hist.t4h, b4)]
    forming_4 = merge([c for c in h1[-4:] if c.t >= b4], 14400)
    if forming_4:
        h4 = h4 + [forming_4]
    today = hist.h1_day[j1 - 1]
    d1 = [c for c, d in zip(hist.d1, hist.d1_day) if d < today and c.t >= T - WINDOW["1d"]]
    k = j1
    while k > 0 and hist.h1_day[k - 1] == today:
        k -= 1
    forming_d = merge(hist.h1[k:j1])
    if forming_d:
        d1 = d1 + [forming_d]
    if real15:
        j15 = bisect_left(hist.t15, T)
        low = hist.m15[bisect_left(hist.t15, T - WINDOW["15m"]):j15]
        spot = hist.m15[bisect_left(hist.t15, T - WINDOW["spot15"]):j15]
    else:
        low = hist.h1[bisect_left(hist.t1h, T - WINDOW["15m"]):j1]
        spot = hist.h1[bisect_left(hist.t1h, T - WINDOW["spot15"]):j1]
    last = low[-1]
    ctx = MarketContext(generated_at=now, analysis_tf="15m", futures_gap=0.0, futures_last=last.c, futures_last_age_s=0)
    for key, tf, cl in (("fut_15m", "15m", low), ("fut_1h", "1h", h1), ("fut_4h", "4h", h4), ("fut_1d", "1d", d1)):
        ctx.candles[key] = CandleSet(key=key, timeframe=tf, kind="futures", source_label=LABEL, candles=cl,
                                     last_is_forming=tf in ("4h", "1d"))
    ctx.candles["spot_15m"] = CandleSet(key="spot_15m", timeframe="15m", kind="spot", source_label=LABEL,
                                        candles=spot, last_is_forming=False)
    for k2, cl in hist.markets.items():
        sec = 86400 if k2.endswith("1d") else 3600
        ctx.markets[k2] = cl[bisect_left(hist.tm[k2], T - WINDOW[k2]):bisect_left(hist.tm[k2], T - sec + 1)]
    ctx.cot = hist.cot
    ctx.spot = SpotQuote(price=last.c, updated_at=now, age_seconds=0, stale=False,
                         price_source="backtest (futures close)")
    return ctx


async def run_hourly(hist: History, spread: float, start_t: int | None = None, end_t: int | None = None,
                     progress=None) -> tuple[list[dict], list[dict], dict, list[dict]]:
    from core.indicators import atr
    start15 = (hist.m15[0].t + WINDOW["15m"] + 3599) // 3600 * 3600 if hist.m15 else 10 ** 12
    end15 = hist.m15[-1].t + 900 if hist.m15 else 0
    # Execution candles: 1H before the real-15m period, 15m inside it.
    ex = [(c, 3600) for c in hist.h1 if c.t + 3600 <= start15] + [(c, 900) for c in hist.m15 if c.t >= start15]
    first_T = hist.h1[0].t + HOURLY_WARMUP_S
    if start_t:
        first_T = max(first_T, start_t)
    last_T = min(end_t or 10 ** 12, ex[-1][0].t)
    trades, calls, steps = [], [], []
    pending, trade, opened, day_pnl, live = None, None, {}, {}, {"losses": {}, "last_loss": 0}
    wf = WalkForward([c.t + s2 for c, s2 in ex], [c.c for c, _ in ex])
    counts = {"steps": 0, "now": 0, "pending": 0, "none": 0, "veto": 0, "pending_cancelled": 0,
              "pending_expired": 0, "skipped_entry": 0}
    started = time.time()
    for n, (c, sec) in enumerate(ex):
        end = c.t + sec
        if trade and trade["entry_t"] <= c.t and exit_on_bar(trade, c, spread, sec):
            trade["bars"] = trade.get("bars", 0) + 1
            trades.append(trade)
            book(day_pnl, trade, live)
            trade = None
        elif trade and trade["entry_t"] <= c.t:
            trade["bars"] = trade.get("bars", 0) + 1
        if pending and not trade:
            p, s = pending["plan"], pending["s"]
            lvl = p.entry_hi if s > 0 else p.entry_lo
            if (c.c - p.stop) * s < 0:
                pending, counts["pending_cancelled"] = None, counts["pending_cancelled"] + 1
            else:
                if (c.l < lvl) if s > 0 else (c.h > lvl):
                    pending["pierced"] = True
                if pending["pierced"] and (c.c - lvl) * s > 0:
                    trade = open_trade(p, "pending", end, c.c, spread, pending["decided_t"])
                    if trade:
                        trade.update(pending["meta"])
                    counts["skipped_entry"] += trade is None
                    pending = None
                elif end - pending["decided_t"] >= PENDING_WINDOW_S:
                    pending, counts["pending_expired"] = None, counts["pending_expired"] + 1

        if end_t and end > end_t and not trade and not pending:
            break
        if end % 3600 or end < first_T or end > last_T or n + 1 >= len(ex):
            continue
        T = end
        real15 = start15 <= T <= end15
        if bisect_left(hist.t1h, T) == 0:
            continue
        ctx = context_hourly(hist, T, real15)
        results, rep = await analyse(ctx, wf.weights(T, calls))
        counts["steps"] += 1
        counts[rep.plan.kind] = counts.get(rep.plan.kind, 0) + 1
        veto = rep.headline.startswith("NO TRADE: data check")
        counts["veto"] += veto
        direction = "BUY" if rep.weighted_score >= 0.15 else "SELL" if rep.weighted_score <= -0.15 else None
        step = {"T": T, "real15": real15, "conf": rep.confidence, "dir": direction, "kind": rep.plan.kind,
                "veto": veto, "agents": {r.agent: (r.status, r.bias, r.confidence) for r in results}}
        steps.append(step)
        for r in results:
            if r.status == "OK" and r.bias in ("BUY", "SELL"):
                calls.append({"agent": r.agent, "bias": r.bias, "t": T, "price": c.c})
        if direction:
            calls.append({"agent": "chief", "bias": direction, "t": T, "price": c.c})

        if not trade:
            plan = rep.plan
            if pending and direction != pending["plan"].side:
                pending, counts["pending_cancelled"] = None, counts["pending_cancelled"] + 1
            meta = {}
            if plan.side:
                h1w = ctx.candles["fut_1h"].candles
                meta = {"conf": rep.confidence, "real15": real15, "score": rep.weighted_score,
                        "agree": sum(r.status == "OK" and r.bias == plan.side for r in results),
                        "against": sum(r.status == "OK" and r.bias not in (plan.side, "WAIT") for r in results),
                        "atr1h": (atr(h1w)[-1] or 0) if len(h1w) > 20 else 0,
                        "biases": {r.agent: r.bias for r in results}}
            why_block = (block_reason(T, opened, day_pnl, abs((plan.entry_lo + plan.entry_hi) / 2 - plan.stop) * 100 * SETTINGS["lot"],
                                      live, ctx, rep)
                         if plan.kind == "now" and plan.stop and plan.t1 else None)
            if why_block:
                counts["blocked_" + why_block] = counts.get("blocked_" + why_block, 0) + 1
            elif plan.kind == "now" and plan.stop and plan.t1:
                pending = None
                nc = ex[n + 1][0]
                trade = open_trade(plan, "now", nc.t, nc.o, spread, T)
                if trade:
                    trade.update(meta)
                    opened[session_day(T)] = opened.get(session_day(T), 0) + 1
                counts["skipped_entry"] += trade is None
            elif plan.kind == "pending" and plan.stop and plan.t1 and not pending:
                pending = {"plan": plan, "s": 1 if plan.side == "BUY" else -1, "decided_t": T, "pierced": False,
                           "meta": meta}
        if progress and counts["steps"] % 10 == 0:
            progress(T - first_T, max(1, last_T - first_T))
        if counts["steps"] % 100 == 0:
            print(f"\r  hourly step {counts['steps']} ({time.time() - started:.0f}s, at {when(T)})   ", end="", flush=True)
    print()
    if not steps:
        raise ValueError("No analysis steps in that period (the first month of 1H history is needed as warm-up).")
    counts["open_at_end"] = 1 if trade else 0
    counts["first_t"], counts["last_t"] = steps[0]["T"], steps[-1]["T"]
    counts["start15"] = start15
    for t in trades:
        t["rr1"] = round(abs(t["t1"] - t["entry"]) / t["risk"], 2)
    ends = [c.t + s for c, s in ex]
    counts["weights_history"] = wf.history
    return trades, calls, counts, steps, (ex, ends)


def score_calls_ex(ex, ends, calls) -> dict:
    out: dict[str, dict] = {}
    for x in calls:
        j = bisect_left(ends, x["t"] + HORIZON_S)
        a = out.setdefault(x["agent"], {"calls": 0, "hits": 0, "misses": 0, "flat": 0, "unscored": 0})
        a["calls"] += 1
        if j >= len(ex):
            a["unscored"] += 1
            continue
        move = (ex[j][0].c - x["price"]) * (1 if x["bias"] == "BUY" else -1)
        a["hits" if move >= MOVE_MIN else "misses" if move <= -MOVE_MIN else "flat"] += 1
    for a in out.values():
        d = a["hits"] + a["misses"]
        a["hit_rate"] = round(100 * a["hits"] / d) if d else None
    return out


def analyse_6m(trades, steps, agents) -> list[str]:
    """Plain-text findings used for the console and the notes file."""
    L = []
    by_month: dict[str, list] = {}
    for t in trades:
        by_month.setdefault(datetime.fromtimestamp(t["entry_t"], timezone.utc).strftime("%Y-%m"), []).append(t)
    L.append("Monthly: " + "; ".join(f"{m} {len(v)} trades {sum(x['r'] for x in v):+.1f}R" for m, v in sorted(by_month.items())))
    stops = [t for t in trades if t["why"].startswith("stop")]
    quick = [t for t in stops if t.get("bars", 99) <= 2]
    L.append(f"Stops hit: {len(stops)} of {len(trades)}; within the first 2 bars: {len(quick)}.")
    if trades:
        sd = [t["risk"] / t["atr1h"] for t in trades if t.get("atr1h")]
        if sd:
            L.append(f"Stop distance in 1H ATRs: median {sorted(sd)[len(sd) // 2]:.2f}, min {min(sd):.2f}, max {max(sd):.2f}.")
        rr = sorted(t["rr1"] for t in trades)
        L.append(f"Target-1 reward:risk at entry: median {rr[len(rr) // 2]:.2f}, min {rr[0]:.2f}, max {rr[-1]:.2f}.")
    for name, f in (("conf>=60", lambda t: t.get("conf", 0) >= 60), ("conf>=70", lambda t: t.get("conf", 0) >= 70),
                    ("agents agree>=4", lambda t: t.get("agree", 0) >= 4), ("agents agree>=5", lambda t: t.get("agree", 0) >= 5),
                    ("conf>=60 and agree>=4", lambda t: t.get("conf", 0) >= 60 and t.get("agree", 0) >= 4)):
        s = summarize([t for t in trades if f(t)])
        L.append(f"Filter {name}: {s['n']} trades, win {s['win_rate']}%, total {s['total_r']:+.2f}R, avg {s['avg_r']}R")
    n = len(steps)
    if n:
        c60 = sum(s["conf"] >= 60 for s in steps)
        L.append(f"Chief confidence >= 60 in {c60} of {n} analyses ({100 * c60 / n:.0f}%); >= 70 in "
                 f"{sum(s['conf'] >= 70 for s in steps)}.")
        names = sorted({a for s in steps for a in s["agents"]})
        for a in names:
            st = [s["agents"][a] for s in steps if a in s["agents"]]
            bad = sum(x[0] != "OK" for x in st)
            ok = [x for x in st if x[0] == "OK"]
            dist = {b: sum(x[1] == b for x in ok) for b in ("BUY", "SELL", "WAIT")}
            hr = agents.get(a, {}).get("hit_rate")
            L.append(f"Agent {a}: not OK {bad}/{len(st)}; bias BUY {dist['BUY']} SELL {dist['SELL']} WAIT {dist['WAIT']}; "
                     f"4h hit rate {hr}%")
    # Skeptic's effect: trades where the Skeptic disagreed with the trade side
    sk_against = [t for t in trades if t.get("biases", {}).get("skeptic") not in (None, "WAIT", t["side"])]
    sk_with = [t for t in trades if t.get("biases", {}).get("skeptic") == t["side"]]
    for name, grp in (("Skeptic against the trade", sk_against), ("Skeptic with the trade", sk_with)):
        s = summarize(grp)
        L.append(f"{name}: {s['n']} trades, win {s['win_rate']}%, total {s['total_r']:+.2f}R")
    tr_with = [t for t in trades if t.get("biases", {}).get("trend") == t["side"]]
    tr_not = [t for t in trades if t.get("biases", {}).get("trend") != t["side"]]
    for name, grp in (("Trend analyst agreed", tr_with), ("Trend analyst did not agree", tr_not)):
        s = summarize(grp)
        L.append(f"{name}: {s['n']} trades, win {s['win_rate']}%, total {s['total_r']:+.2f}R")
    return L


async def main_hourly(args) -> None:
    hist = History(load_data(args.refresh, args.offline))
    print(f"Replaying ~6 months on hourly steps ({len(hist.h1)} 1H candles, {len(hist.m15)} 15m candles)...")
    trades, calls, counts, steps, (ex, ends) = await run_hourly(hist, args.spread)
    s = summarize(trades)
    groups = {"Approximated period (1H as lowest TF)": summarize([t for t in trades if not t.get("real15")]),
              "Real 15m period": summarize([t for t in trades if t.get("real15")]),
              "BUY trades": summarize([t for t in trades if t["side"] == "BUY"]),
              "SELL trades": summarize([t for t in trades if t["side"] == "SELL"]),
              "BUY/SELL NOW plans": summarize([t for t in trades if t["kind"] == "now"]),
              "WAIT then BUY/SELL plans": summarize([t for t in trades if t["kind"] == "pending"]),
              "Chief confidence >= 60": summarize([t for t in trades if t.get("conf", 0) >= 60]),
              "Chief confidence >= 70": summarize([t for t in trades if t.get("conf", 0) >= 70]),
              ">= 4 agents agree with the side": summarize([t for t in trades if t.get("agree", 0) >= 4]),
              ">= 5 agents agree with the side": summarize([t for t in trades if t.get("agree", 0) >= 5])}
    agents = score_calls_ex(ex, ends, calls)
    lines = plain_summary(s, groups, agents, counts, args.spread)
    lines.insert(1, f"Hourly steps. Before {when(counts['start15'])} the lowest timeframe is APPROXIMATED with 1H "
                    f"candles (the free data has only ~1 month of 15m); after it, real 15m candles are used.")
    findings = analyse_6m(trades, steps, agents)
    print("\n=== RESULTS (6 months, hourly) ===")
    for x in lines + [""] + findings:
        print(x)
    page = html_report(s, groups, agents, trades, counts, lines + findings, args.spread)
    page = page.replace("gold futures 15m candles", "hourly steps over ~6 months (15m where available)")
    page = page.replace("This test covers only about a month and a small number\nof trades",
                        "This test covers about 6 months, partly with 1H standing in for 15m, and a limited number\nof trades")
    REPORT_6M.write_text(page, encoding="utf-8")
    dump = ROOT / "data" / "backtest_6m_trades.json"
    dump.write_text(json.dumps({"counts": counts, "trades": trades, "agents": agents, "findings": findings,
                                "steps": [{k: v for k, v in x.items() if k != "agents"} for x in steps]},
                               default=str, indent=1), encoding="utf-8")
    print(f"\nReport written to {REPORT_6M}")


# ---------------------------------------------------------------- dashboard runs (JSON out)
def data_range(hist: History) -> dict:
    """Earliest start for each step mode, and the latest data time."""
    return {"first_1h": hist.h1[0].t + HOURLY_WARMUP_S, "first_15m": hist.m15[0].t + WINDOW["15m"],
            "last": hist.m15[-1].t + 900 if hist.m15 else hist.h1[-1].t + 3600}


async def web_run(start_t: int, end_t: int, step: str, spread: float, progress_file: Path | None,
                  settings: dict | None = None) -> dict:
    """One backtest for the dashboard's Backtest tab: same engines, period-limited, results as plain JSON."""
    def report(done, total, phase="Replaying history"):
        if progress_file:
            progress_file.write_text(json.dumps({"done": done, "total": total, "phase": phase}))

    SETTINGS.update(settings or {})
    report(0, 1, "Loading data")
    hist = History(load_data(False, False))
    rng = data_range(hist)
    if step == "auto":               # 15m steps for up to ~6 weeks (precise); longer periods step hourly (faster)
        step = "15m" if start_t >= rng["first_15m"] and end_t - start_t <= 45 * 86400 else "1h"
    if step == "15m":
        trades, calls, counts = await run(hist, spread, None, start_t, end_t, report)
        steps = counts.pop("_steps", [])
        for st in steps:                     # score every agent call 4 hours later (same rule as the track record)
            j = bisect_left(hist.t15, st["t"] + HORIZON_S - 900)
            if j >= len(hist.m15):
                continue
            for a in st["ag"]:
                if a[1] in ("BUY", "SELL"):
                    mv = (hist.m15[j].c - st["p"]) * (1 if a[1] == "BUY" else -1)
                    a[3] = "hit" if mv >= MOVE_MIN else "miss" if mv <= -MOVE_MIN else "flat"
        agents = score_calls(hist, calls)
        groups = {}
    else:
        trades, calls, counts, steps, (ex, ends) = await run_hourly(hist, spread, start_t, end_t, report)
        agents = score_calls_ex(ex, ends, calls)
        groups = {"Approximated period (1H as lowest TF)": summarize([t for t in trades if not t.get("real15")]),
                  "Real 15m period": summarize([t for t in trades if t.get("real15")])}
    report(1, 1, "Scoring")
    s = summarize(trades)
    groups = {"BUY trades": summarize([t for t in trades if t["side"] == "BUY"]),
              "SELL trades": summarize([t for t in trades if t["side"] == "SELL"]),
              "BUY/SELL NOW plans": summarize([t for t in trades if t["kind"] == "now"]),
              "WAIT then BUY/SELL plans": summarize([t for t in trades if t["kind"] == "pending"]),
              "Chief confidence >= 60%": summarize([t for t in trades if t.get("conf", 0) >= 60]),
              "Chief confidence >= 70%": summarize([t for t in trades if t.get("conf", 0) >= 70]), **groups}
    usd = add_dollars(trades)
    lines = plain_summary(s, groups, agents, counts, spread)
    if trades:
        lines.insert(3, f"In dollars at {SETTINGS['lot']} lot on a ${SETTINGS['account']:,.0f} account: "
                        f"{usd['total_usd']:+,.0f} ({usd['return_pct']:+.1f}%), ending balance ${usd['end_balance']:,.0f}, "
                        f"worst drop ${usd['max_dd_usd']:,.0f}, average risk per trade ${usd['avg_risk_usd']:,.0f}.")
    if step == "1h":
        lines.insert(1, "Hourly steps: before about one month ago the lowest timeframe is approximated with 1H candles "
                        "(free data has only ~1 month of 15m), so treat that part as a rough guide.")
    eq, curve = 0.0, []
    for t in trades:
        eq += t["r"]
        curve.append([t["exit_t"], round(eq, 2)])
    keep = ("side", "kind", "decided_t", "entry_t", "entry", "stop", "t1", "exit_t", "exit", "why", "r", "conf",
            "usd", "balance")
    out_steps = steps if step == "15m" else []
    return {"steps": out_steps, "params": {"start": start_t, "end": end_t, "step": step, "spread": spread, **SETTINGS},
            "summary": s, "usd": usd, "groups": groups, "agents": agents, "lines": lines, "counts": counts,
            "equity": curve, "trades": [{k: t.get(k) for k in keep} for t in trades], "made_at": time.time()}


# ---------------------------------------------------------------- health check
# One replay of the agents, then the Chief and the trade rules re-run for each variant: today's rules, without the
# live-only rules, harsh costs, each quality filter, and each voting agent left out. Every variant is also split
# into the first and second half of the period: a change only counts as real if it helps in both halves.
NOISE_USD = 25.0          # differences smaller than this per half count as "no difference"


def _variants() -> list[dict]:
    v = [{"key": "base", "group": "base", "label": "Today's rules (as live)", "set": {}},
         {"key": "no_live", "group": "rules", "label": "Without the live-only rules (2 losses, cool-down, chase)",
          "set": {"live_rules": False}},
         {"key": "harsh", "group": "costs", "label": "Harsh costs: double spread + $0.50 stop slippage",
          "set": {"stop_slip": 0.5}, "spread_mult": 2.0},
         {"key": "f_session", "group": "filter", "label": "Only 07:00 London to 12:00 New York", "set": {"f_session": True}},
         {"key": "f_trend", "group": "filter", "label": "Only when Daily and 4H agree", "set": {"f_trend": True}},
         {"key": "f_hunt", "group": "filter", "label": "Only right after a stop hunt", "set": {"f_hunt": True}}]
    off = set(votes.off())
    for a in BUILT_IN:
        if BASE_WEIGHTS.get(a.name, 0) > 0 and a.name not in off:
            v.append({"key": "drop_" + a.name, "group": "agent", "agent": a.name,
                      "label": f"Without {AGENT_NAMES.get(a.name, a.name)}", "set": {"drop": [a.name]}})
    for name in sorted(off):
        if BASE_WEIGHTS.get(name, 0) > 0:
            v.append({"key": "add_" + name, "group": "agent_add", "agent": name,
                      "label": f"{AGENT_NAMES.get(name, name)} vote back on", "set": {"add": [name]}})
    return v


def _verdict(v: dict, base: dict) -> tuple[str, str]:
    d1, d2 = v["h1_usd"] - base["h1_usd"], v["h2_usd"] - base["h2_usd"]
    better = d1 > NOISE_USD and d2 > NOISE_USD
    worse = d1 < -NOISE_USD and d2 < -NOISE_USD
    few = v["n"] < 15
    g = v["group"]
    if g == "costs":
        return ("survives", "Still profitable with worse fills.") if v["usd"] > 0 else \
               ("fails", "The profit disappears with worse fills: the edge is too thin for real trading.")
    if g == "agent":                       # removing the agent made it better / worse
        if worse:
            return "useful", "Results get worse in both halves without it: it helps."
        if better:
            return "hurts", "Results get better in both halves without it: consider removing it or cutting its weight."
        return "noise", "No clear effect either way: its vote adds little."
    if g == "agent_add":                   # its vote is off now: would switching it back on help?
        if better:
            return "helps", "Better in both halves with its vote back on."
        if worse:
            return "hurts", "Worse in both halves with its vote: keep it off."
        return "noise", "No clear effect either way."
    tag = ("helps", "Better in both halves.") if better else ("hurts", "Worse in both halves.") if worse else \
          ("mixed", "Better in one half only: could be luck, don't adopt yet.")
    if few and tag[0] == "helps":
        return "promising", f"Better in both halves, but only {v['n']} trades: needs a longer test."
    return tag


async def health_check(start_t: int, end_t: int, step: str, spread: float, progress_file: Path | None,
                       variants: list[dict] | None = None, keep_cache: bool = False, report=None) -> dict:
    if report is None:
        def report(done, total, phase):
            if progress_file:
                progress_file.write_text(json.dumps({"done": done, "total": total, "phase": phase}))

    report(0, 1, "Loading data")
    hist = History(load_data(False, False))
    rng = data_range(hist)
    if step == "auto":               # 15m steps for up to ~6 weeks (precise); longer periods step hourly (faster)
        step = "15m" if start_t >= rng["first_15m"] and end_t - start_t <= 45 * 86400 else "1h"
    base_settings = dict(SETTINGS, cache=True, cache_ns=step)
    variants, out = variants or _variants(), []
    for k, v in enumerate(variants):
        SETTINGS.clear()
        SETTINGS.update(base_settings, **v["set"])
        sp = spread * v.get("spread_mult", 1.0)
        phase = f"{k + 1} of {len(variants)}: {v['label']}" + (" (agents run once here, the rest is quicker)" if k == 0 else "")
        prog = lambda d, n, *_: report(k + d / max(n, 1), len(variants), phase)          # noqa: E731
        if step == "15m":
            trades, _calls, counts = await run(hist, sp, None, start_t, end_t, prog)
            counts.pop("_steps", None)
        else:
            trades, _calls, counts, _steps, _ex = await run_hourly(hist, sp, start_t, end_t, prog)
        usd = add_dollars(trades)
        mid = (counts["first_t"] + counts["last_t"]) / 2
        half = [[t for t in trades if t["entry_t"] < mid], [t for t in trades if t["entry_t"] >= mid]]
        sm = summarize(trades)
        out.append({k2: v[k2] for k2 in ("key", "group", "label", "agent") if k2 in v} | {
            "n": sm["n"], "win_rate": sm["win_rate"], "usd": usd["total_usd"], "dd": usd["max_dd_usd"],
            "h1_usd": round(sum(t["usd"] for t in half[0]), 2), "h2_usd": round(sum(t["usd"] for t in half[1]), 2),
            "h1_n": len(half[0]), "h2_n": len(half[1]),
            "blocked": {x[8:]: c for x, c in counts.items() if x.startswith("blocked_")}})
        if k == 0:
            first_t, last_t, mid0 = counts["first_t"], counts["last_t"], mid
    SETTINGS.clear()
    SETTINGS.update(base_settings, cache=False)
    base = out[0]
    for v in out[1:]:
        v["verdict"], v["note"] = _verdict(v, base)
    base["verdict"], base["note"] = ("survives", "Profitable over the period.") if base["usd"] > 0 else \
                                    ("fails", "Lost money over the period.")
    if (base["h1_usd"] > 0) != (base["h2_usd"] > 0):
        base["note"] += " One half made money and the other lost: results are not stable yet."
    if not keep_cache:
        _AGENT_CACHE.clear()
    return {"kind": "health", "made_at": time.time(), "variants": out, "votes_off": votes.off(),
            "params": {"start": start_t, "end": end_t, "step": step, "spread": spread, "first_t": first_t,
                       "last_t": last_t, "mid": mid0, "account": SETTINGS["account"], "lot": SETTINGS["lot"],
                       "day_max_loss": SETTINGS["day_max_loss"], "day_max_profit": SETTINGS["day_max_profit"]}}


# ---------------------------------------------------------------- review board
# Weekly: re-test every agent's vote on 6 months (hourly) and on the last month (15m). A vote is switched off only if
# the 6-month test is better without it in BOTH halves and the last month is not worse; a switched-off vote comes back
# on by the same rule. At most 2 changes per review, never fewer than MIN_VOTERS voting agents, and when there are 2
# changes they must also pass together. Control rules (discipline, limits, news) are never changed by the board.
MAX_CHANGES = 2


def _gain(v: dict, base: dict) -> float:
    return v["usd"] - base["usd"]


def _beats(v: dict, base: dict) -> bool:
    return v["h1_usd"] - base["h1_usd"] > NOISE_USD and v["h2_usd"] - base["h2_usd"] > NOISE_USD


async def review(progress_file: Path | None, apply: bool) -> dict:
    def stage(start, width, label):
        def r(done, n, phase):
            if progress_file:
                progress_file.write_text(json.dumps({"done": start + width * done / max(n, 1), "total": 1,
                                                     "phase": f"{label} · {phase}"}))
        return r

    hist = History(load_data(False, False))
    rng = data_range(hist)
    last = int(rng["last"])
    windows = {"6 months": (max(int(rng["first_1h"]), last - 183 * 86400), "1h"),
               "last month": (max(int(rng["first_15m"]), last - 29 * 86400), "15m")}
    off_now = votes.off()
    results = {}
    for k, (name, (start, step)) in enumerate(windows.items()):
        results[name] = await health_check(start, last + 1, step, 0.30, None, _variants(), keep_cache=True,
                                           report=stage(0.4 * k, 0.4, f"Testing every agent on the {name}"))
    six, month = results["6 months"], results["last month"]
    b6, bm = six["variants"][0], month["variants"][0]
    mv = {v["key"]: v for v in month["variants"]}
    cands = []
    for v in six["variants"]:
        if v["group"] not in ("agent", "agent_add"):
            continue
        m = mv.get(v["key"])
        if m and _beats(v, b6) and _gain(m, bm) >= -NOISE_USD:
            cands.append({"agent": v["agent"], "action": "off" if v["group"] == "agent" else "on",
                          "gain_6m": round(_gain(v, b6), 2), "gain_month": round(_gain(m, bm), 2),
                          "halves_6m": [round(v["h1_usd"] - b6["h1_usd"], 2), round(v["h2_usd"] - b6["h2_usd"], 2)]})
    cands.sort(key=lambda c: -(c["gain_6m"] + c["gain_month"]))
    voters = len([a for a in BASE_WEIGHTS if BASE_WEIGHTS[a] > 0]) - len(off_now)
    chosen = []
    for c in cands:
        if len(chosen) >= MAX_CHANGES:
            break
        after = voters - sum(x["action"] == "off" for x in chosen) - (c["action"] == "off") + sum(x["action"] == "on" for x in chosen)
        if c["action"] == "off" and after < votes.MIN_VOTERS:
            c["skipped"] = f"would leave fewer than {votes.MIN_VOTERS} voting agents"
            continue
        chosen.append(c)
    confirm = None
    if len(chosen) > 1:                      # several changes: they must also work together
        drop = [c["agent"] for c in chosen if c["action"] == "off"]
        add = [c["agent"] for c in chosen if c["action"] == "on"]
        combo = [{"key": "base", "group": "base", "label": "Today's votes", "set": {}},
                 {"key": "combo", "group": "combo", "label": "All proposed changes together", "set": {"drop": drop, "add": add}}]
        confirm = {}
        for k, (name, (start, step)) in enumerate(windows.items()):
            r = await health_check(start, last + 1, step, 0.30, None, combo, keep_cache=True,
                                   report=stage(0.8 + 0.1 * k, 0.1, f"Checking the changes together on the {name}"))
            confirm[name] = r["variants"]
        ok = _beats(confirm["6 months"][1], confirm["6 months"][0]) and \
            _gain(confirm["last month"][1], confirm["last month"][0]) >= -NOISE_USD
        if not ok:
            chosen = chosen[:1]              # together they don't hold up: only the strongest single change
            confirm["result"] = "Together they did not hold up, so only the strongest change was kept."
        else:
            confirm["result"] = "The changes also work together."
    _AGENT_CACHE.clear()
    new_off = set(off_now)
    for c in chosen:
        (new_off.add if c["action"] == "off" else new_off.discard)(c["agent"])
    summary = ("No changes: no agent's vote clearly helped or hurt in both halves of the 6 months while the last month "
               "agreed." if not chosen else "; ".join(
                   f"{AGENT_NAMES.get(c['agent'], c['agent'])} vote {c['action'].upper()} "
                   f"(6 months {c['gain_6m']:+,.0f} $, last month {c['gain_month']:+,.0f} $)" for c in chosen) + ".")
    return {"kind": "review", "made_at": time.time(), "apply": apply, "votes_before": off_now, "votes_after": sorted(new_off),
            "changes": chosen, "candidates": cands, "confirm": confirm, "summary": summary,
            "windows": {k: {"variants": r["variants"], "params": r["params"]} for k, r in results.items()},
            "rules": {"noise_usd": NOISE_USD, "max_changes": MAX_CHANGES, "min_voters": votes.MIN_VOTERS}}


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest the XAUUSD dashboard's trade plans on past data.")
    ap.add_argument("--spread", type=float, default=0.30, help="cost per side in dollars (default 0.30)")
    ap.add_argument("--refresh", action="store_true", help="download fresh data even if the cache is recent")
    ap.add_argument("--offline", action="store_true", help="use only the cached data, no internet")
    ap.add_argument("--days", type=float, default=None, help="only test the last N days (faster)")
    ap.add_argument("--step", choices=["15m", "1h"], default="15m",
                    help="15m (default, ~1 month) or 1h (~6 months; 1H stands in for 15m where no 15m data exists)")
    ap.add_argument("--start", help="dashboard run: first day YYYY-MM-DD (UTC)")
    ap.add_argument("--end", help="dashboard run: last day YYYY-MM-DD (UTC, inclusive)")
    ap.add_argument("--auto", action="store_true", help="dashboard run: pick 15m or 1h steps from the period")
    ap.add_argument("--target-rr", type=float, default=None, help="fixed reward:risk target (e.g. 1.15) instead of the plan's")
    ap.add_argument("--no-partial", action="store_true", help="do not take half profit at 1R")
    ap.add_argument("--no-news", action="store_true", help="ignore the news filter (to compare with/without)")
    ap.add_argument("--static-weights", action="store_true", help="fixed agent weights (the default)")
    ap.add_argument("--perf-weights", action="store_true", help="weekly performance weights (walk-forward)")
    ap.add_argument("--account", type=float, default=25000, help="account size in dollars for the $ results")
    ap.add_argument("--lot", type=float, default=0.1, help="fixed lot per trade (1 lot = 100 oz)")
    ap.add_argument("--day-max-loss", type=float, default=350, help="stop new trades for the day at this $ loss (0 = off)")
    ap.add_argument("--day-max-profit", type=float, default=150, help="stop new trades for the day at this $ profit (0 = off)")
    ap.add_argument("--no-live-rules", action="store_true", help="leave out 2 losses/day, the cool-down and the chase filter")
    ap.add_argument("--stop-slip", type=float, default=0.0, help="extra $ lost when a stop fills (cost stress test)")
    ap.add_argument("--only-session", action="store_true", help="filter: only 07:00 London to 12:00 New York")
    ap.add_argument("--only-trend", action="store_true", help="filter: only when Daily and 4H agree with the trade")
    ap.add_argument("--only-hunt", action="store_true", help="filter: only right after a stop hunt")
    ap.add_argument("--health-check", action="store_true", help="dashboard run: compare today's rules with variants")
    ap.add_argument("--review", action="store_true", help="review board: re-test every agent's vote (6 months + last month)")
    ap.add_argument("--dry-run", action="store_true", help="review board: suggest changes only, don't apply them")
    ap.add_argument("--json-out", help="dashboard run: write results as JSON to this file")
    ap.add_argument("--progress-file", help="dashboard run: keep progress in this file")
    args = ap.parse_args()
    SETTINGS.update(day_max_loss=args.day_max_loss, day_max_profit=args.day_max_profit)
    SETTINGS.update(target_rr=args.target_rr, partial=not args.no_partial, account=args.account, lot=args.lot,
                    news=not args.no_news, adaptive=args.perf_weights and not args.static_weights)
    SETTINGS.update(live_rules=not args.no_live_rules, stop_slip=args.stop_slip, f_session=args.only_session,
                    f_trend=args.only_trend, f_hunt=args.only_hunt)
    if args.json_out:
        day = lambda d: int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        out, prog = Path(args.json_out), Path(args.progress_file) if args.progress_file else None
        try:
            if args.review:
                res = asyncio.run(review(prog, apply=not args.dry_run))
                rid = out.stem
                if res["changes"] and res["apply"]:
                    votes.change(res["votes_after"], "review board", res["changes"], res["summary"], rid)
                    res["applied"] = True
            elif args.health_check:
                res = asyncio.run(health_check(day(args.start), day(args.end) + 86400, "auto" if args.auto else args.step,
                                               args.spread, prog))
            else:
                res = asyncio.run(web_run(day(args.start), day(args.end) + 86400, "auto" if args.auto else args.step,
                                          args.spread, prog, dict(SETTINGS)))
            out.write_text(json.dumps(res, default=str), encoding="utf-8")
        except Exception as e:  # noqa: BLE001 - the dashboard shows the message
            out.write_text(json.dumps({"error": f"{type(e).__name__}: {e}"}), encoding="utf-8")
        return
    if args.step == "1h":
        print("Loading data...")
        asyncio.run(main_hourly(args))
        return

    print("Loading data...")
    hist = History(load_data(args.refresh, args.offline))
    print(f"Replaying history ({len(hist.m15)} 15m candles available)...")
    trades, calls, counts = asyncio.run(run(hist, args.spread, args.days))
    s = summarize(trades)
    groups = {"BUY trades": summarize([t for t in trades if t["side"] == "BUY"]),
              "SELL trades": summarize([t for t in trades if t["side"] == "SELL"]),
              "BUY/SELL NOW plans": summarize([t for t in trades if t["kind"] == "now"]),
              "WAIT then BUY/SELL plans": summarize([t for t in trades if t["kind"] == "pending"])}
    agents = score_calls(hist, calls)
    lines = plain_summary(s, groups, agents, counts, args.spread)

    print("\n=== RESULTS ===")
    for x in lines:
        print(x)
    print("\n4-hour direction hit rate per agent (hit = moved $3+ its way, miss = $3+ against):")
    for a, v in sorted(agents.items(), key=lambda x: x[0] == "chief"):
        hr = f"{v['hit_rate']}%" if v["hit_rate"] is not None else "n/a"
        print(f"  {AGENT_NAMES.get(a, a):28s} {hr:>5s}  ({v['hits']} right, {v['misses']} wrong, {v['flat']} flat, "
              f"{v['calls']} calls)")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(html_report(s, groups, agents, trades, counts, lines, args.spread), encoding="utf-8")
    print(f"\nReport written to {REPORT}  (open it in your browser)")


if __name__ == "__main__":
    main()
