"""Fetches live data from XAUS and turns it into ONE shared MarketContext for all agents.

Rules (verified against the live API):
- Spot price: /spot?compact=1 -> spot_usd_oz. Staleness is decided HERE from updated_at vs the
  clock; the API's data_state is kept only for display and never trusted on its own.
- Spot candles: aggregated from /intraday 2-minute samples (no true 1m candles possible).
- /chart and /history are gold FUTURES (Yahoo GC=F), not spot. They are labelled as such.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone

import httpx

from . import cot, news
from .models import Candle, CandleSet, DailyBar, MarketContext, SpotQuote

API = "https://xaus.com/api/v1"
API_KEY = os.getenv("XAUS_API_KEY")   # optional; XAUS needs no key
STALE_AFTER_S = 180
CACHE_S = 20
MIN_SAMPLES_PER_CANDLE = 3

TF_SECONDS = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
SPOT_LABEL = "Spot XAU/USD · aggregated from 2-min samples (xaus sampler, gold-api.com)"
FUT_LABEL = "Gold FUTURES (COMEX GC=F) · real OHLCV via Yahoo Finance proxy · delayed"

_cache: dict = {"at": 0.0, "raw": None}
_lock = asyncio.Lock()


async def _get(client: httpx.AsyncClient, path: str):
    headers = {"X-Api-Key": API_KEY} if API_KEY else {}
    r = await client.get(API + path, headers=headers)
    if r.status_code == 503:
        raise RuntimeError(f"{path}: no data available (HTTP 503)")
    r.raise_for_status()
    return r.json()


async def _fetch_raw() -> dict:
    paths = {
        "spot": "/spot?compact=1",
        "intraday": "/intraday?symbol=xau&hours=48",
        "fut_1m": "/chart?symbol=xau&interval=1m&range=1d",
        "fut_5m": "/chart?symbol=xau&interval=5m&range=5d",
        "fut_15m": "/chart?symbol=xau&interval=15m&range=5d",
        "fut_1h": "/chart?symbol=xau&interval=1h&range=3mo",
        "history": "/history",
        "fut_1d": "/chart?symbol=xau&interval=1d&range=2y",
        "dxy_1h": "/chart?symbol=dxy&interval=1h&range=1mo",
        "silver_1h": "/chart?symbol=silver&interval=1h&range=1mo",
        "sp500_1d": "/chart?symbol=sp500&interval=1d&range=3mo",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(*(_get(client, p) for p in paths.values()), return_exceptions=True)
        raw = dict(zip(paths.keys(), results))
        failed = [k for k, v in raw.items() if isinstance(v, Exception)]
        if failed:   # one retry for brief network hiccups
            retry = await asyncio.gather(*(_get(client, paths[k]) for k in failed), return_exceptions=True)
            raw.update(zip(failed, retry))
    return raw


def aggregate(points: list[dict], sec: int) -> list[Candle]:
    """Group samples ({t,p}) or bars ({t,o,h,l,c,v}) into candles of `sec` seconds."""
    out: list[Candle] = []
    for pt in points:
        p = pt.get("p")
        o, h, l, c = pt.get("o", p), pt.get("h", p), pt.get("l", p), pt.get("c", p)
        if None in (o, h, l, c):
            continue
        t = int(pt["t"]) // sec * sec
        if out and out[-1].t == t:
            last = out[-1]
            last.h, last.l, last.c = max(last.h, h), min(last.l, l), c
            last.v += pt.get("v") or 0
        else:
            out.append(Candle(t=t, o=o, h=h, l=l, c=c, v=pt.get("v") or 0))
    return out


def _sample_interval(d: dict, pts: list[dict]) -> int:
    """Current sampling interval: the API's interval_seconds, or the median spacing of recent samples."""
    recent = [pts[i]["t"] - pts[i - 1]["t"] for i in range(max(1, len(pts) - 30), len(pts))]
    measured = sorted(recent)[len(recent) // 2] if recent else 0
    return int(max(d.get("interval_seconds") or 0, round(measured / 60) * 60, 60))


def _add_tick(candles: list[Candle], price: float, t: float, sec: int) -> None:
    bucket = int(t) // sec * sec
    if not candles or bucket > candles[-1].t:
        candles.append(Candle(t=bucket, o=price, h=price, l=price, c=price))
    elif bucket == candles[-1].t:
        last = candles[-1]
        last.h, last.l, last.c = max(last.h, price), min(last.l, price), price


def _build(raw: dict, tf: str) -> MarketContext:
    now = datetime.now(timezone.utc)
    now_s = now.timestamp()
    ctx = MarketContext(generated_at=now, analysis_tf=tf)

    def err(name: str) -> bool:
        if isinstance(raw.get(name), Exception):
            e = raw[name]
            ctx.errors.append(f"{name}: {type(e).__name__}{': ' + str(e) if str(e) else ''}")
            return True
        return False

    # Spot quote
    if not err("spot"):
        d = raw["spot"]
        price = d.get("spot_usd_oz") or (d.get("xau") or {}).get("price")
        upd = d.get("updated_at")
        if price and upd:
            updated = datetime.fromisoformat(upd.replace("Z", "+00:00"))
            age = now_s - updated.timestamp()
            ctx.spot = SpotQuote(price=float(price), updated_at=updated, age_seconds=round(age, 1),
                                 stale=age > STALE_AFTER_S, price_source=d.get("price_source", "unknown"),
                                 api_data_state=d.get("data_state") or {})
        else:
            ctx.errors.append("spot: response had no price or updated_at")

    # Spot candles from intraday samples (+ live tick). The sampling interval has changed before
    # (2 min -> 5 min), so read it live and only build candles holding at least 3 samples.
    if not err("intraday"):
        d = raw["intraday"]
        pts = [p for p in d.get("points", []) if p.get("p") is not None]
        ctx.intraday_coverage_s = d.get("coverage_seconds")
        ctx.intraday_interval_s = _sample_interval(d, pts)
        label = SPOT_LABEL.replace("2-min", f"{ctx.intraday_interval_s / 60:g}-min")
        for name, sec in TF_SECONDS.items():
            if sec < MIN_SAMPLES_PER_CANDLE * ctx.intraday_interval_s:
                continue
            cs = aggregate(pts, sec)
            if ctx.spot:
                _add_tick(cs, ctx.spot.price, ctx.spot.updated_at.timestamp(), sec)
            ctx.candles[f"spot_{name}"] = CandleSet(key=f"spot_{name}", timeframe=name, kind="spot",
                                                    source_label=label, candles=cs)

    # Futures candles
    def fut_set(name: str, pts: list[dict], sec: int | None = None) -> None:
        cs = aggregate(pts, sec) if sec else [Candle(t=p["t"], o=p["o"], h=p["h"], l=p["l"], c=p["c"], v=p.get("v") or 0)
                                               for p in pts if None not in (p.get("o"), p.get("h"), p.get("l"), p.get("c"))]
        ctx.candles[f"fut_{name}"] = CandleSet(key=f"fut_{name}", timeframe=name, kind="futures",
                                               source_label=FUT_LABEL + (" · 4h built from 1h" if name == "4h" else ""),
                                               candles=cs)

    if not err("fut_1d"):
        fut_set("1d", raw["fut_1d"].get("points", []))
    for key in ("dxy_1h", "silver_1h", "sp500_1d"):
        if not err(key):
            ctx.markets[key] = [Candle(t=p["t"], o=p["o"], h=p["h"], l=p["l"], c=p["c"], v=p.get("v") or 0)
                                for p in raw[key].get("points", [])
                                if None not in (p.get("o"), p.get("h"), p.get("l"), p.get("c"))]
    for name in ("5m", "15m"):
        if not err(f"fut_{name}"):
            fut_set(name, raw[f"fut_{name}"].get("points", []))
    if not err("fut_1h"):
        pts = raw["fut_1h"].get("points", [])
        fut_set("1h", pts)
        fut_set("4h", pts, TF_SECONDS["4h"])
    if not err("fut_1m"):
        pts = [p for p in raw["fut_1m"].get("points", []) if p.get("c") is not None]
        if pts:
            ctx.futures_last = float(pts[-1]["c"])
            ctx.futures_last_age_s = round(now_s - pts[-1]["t"], 0)
            if ctx.spot:
                ctx.futures_gap = round(ctx.futures_last - ctx.spot.price, 2)

    # Daily (futures) history
    if not err("history"):
        d = raw["history"]
        ctx.daily = [DailyBar(**p) for p in d.get("points", []) if None not in (p.get("c"), p.get("h"), p.get("l"))]
        ctx.daily_source = d.get("price_source", "unknown")

    return ctx


async def build_context(tf: str = "15m") -> MarketContext:
    async with _lock:
        if _cache["raw"] is None or time.time() - _cache["at"] > CACHE_S:
            raw = await _fetch_raw()
            _cache["raw"] = raw
            # Keep a failed fetch for 3 s only, so the next refresh tries again.
            ok = not any(isinstance(v, Exception) for v in raw.values())
            _cache["at"] = time.time() if ok else time.time() - CACHE_S + 3
        raw = _cache["raw"]
    ctx = _build(raw, tf)
    ctx.cot = await cot.load_async()
    await asyncio.to_thread(news.refresh_feed)     # this week's high-impact USD events
    return ctx
