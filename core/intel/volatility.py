"""Volatility regime, expansion/contraction and stop cap, from closed 15m candles.

Thresholds are never hand-picked: `fit_vol` measures them on history (data before `until`), the CLI
`python -m core.intel.fit` stores them in data/intel_params.json. ATR is compared as a fraction of price so
gold at $1,600 and at $4,500 are on the same scale.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.indicators import atr

PARAMS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "intel_params.json"
SLOPE_BARS = 6          # ATR change over the last 6 bars (1.5 h on 15m)
SLOPE_EDGE = 0.10       # +-10% = expanding / contracting
LOOKBACK = 24           # 6 h window for the proxy stop distance in fit_vol


@dataclass
class VolResult:
    regime: str             # low | normal | high | abnormal | unknown
    trend: str              # expanding | contracting | flat | unknown
    atr: float | None
    atr_ratio: float | None  # ATR / price
    slope: float | None
    max_stop: float | None   # k x ATR15
    text: str


@dataclass
class StopCheck:
    ok: bool
    distance: float
    cap: float | None
    text: str


def load_params(path: Path | None = None) -> dict:
    try:
        return json.loads((path or PARAMS_PATH).read_text())
    except (OSError, ValueError):
        return {}


def fit_vol(candles, until: int | None = None) -> dict:
    """Fit regime bands (ATR/price percentiles) and stop cap k from candles with t < until (no look-ahead).

    stop_k = 99th percentile, over history, of the distance a typical protective stop would sit from price
    (beyond the extreme of the last 6 h, as the Chief places stops beyond liquidity) measured in ATR.
    """
    cs = [c for c in candles if until is None or c.t < until]
    a = atr(cs)
    ratios, dist = [], []
    for i in range(LOOKBACK, len(cs)):
        if a[i]:
            ratios.append(a[i] / cs[i].c)
            w = cs[i - LOOKBACK:i]
            dist.append(max(cs[i].c - min(c.l for c in w), max(c.h for c in w) - cs[i].c) / a[i])
    if len(ratios) < 100:
        raise ValueError("not enough history to fit volatility parameters")
    p = np.percentile(ratios, [20, 80, 99])
    return {"atr_ratio": {"low": float(p[0]), "high": float(p[1]), "abnormal": float(p[2])},
            "stop_k": float(np.percentile(dist, 99)), "n": len(ratios)}


def regime(candles, params: dict | None = None) -> VolResult:
    params = params if params is not None else load_params().get("vol", {})
    a = atr(candles) if candles else []
    if not a or a[-1] is None or not params:
        return VolResult("unknown", "unknown", a[-1] if a else None, None, None, None,
                         "Volatility regime unknown (not enough data or thresholds not fitted yet).")
    cur, px = a[-1], candles[-1].c
    r, b = cur / px, params["atr_ratio"]
    reg = "low" if r < b["low"] else "normal" if r < b["high"] else "high" if r < b["abnormal"] else "abnormal"
    prev = a[-1 - SLOPE_BARS] if len(a) > SLOPE_BARS else None
    slope = (cur / prev - 1) if prev else None
    trend = "unknown" if slope is None else "expanding" if slope > SLOPE_EDGE else \
        "contracting" if slope < -SLOPE_EDGE else "flat"
    cap = params["stop_k"] * cur
    words = {"low": "Quiet market: moves are small, expect slow price action.",
             "normal": "Normal volatility.",
             "high": "Volatility is high: wider swings, size carefully.",
             "abnormal": "Volatility is abnormally high, among the biggest 1% in history: avoid new trades."}
    extra = {"expanding": " Volatility is expanding.", "contracting": " Volatility is contracting.",
             "flat": "", "unknown": ""}[trend]
    return VolResult(reg, trend, cur, r, slope, cap, words[reg] + extra)


def stop_check(plan: dict, candles, params: dict | None = None) -> StopCheck:
    """Is the planned stop within k x ATR of the entry? Only reports; never widens or moves the stop."""
    params = params if params is not None else load_params().get("vol", {})
    ent = (plan["entry_lo"] + plan["entry_hi"]) / 2
    dist = abs(ent - plan["stop"])
    a = atr(candles) if candles else []
    if not a or a[-1] is None or not params:
        return StopCheck(True, dist, None, "Stop cap not checked (no ATR or thresholds yet).")
    cap = params["stop_k"] * a[-1]
    if dist > cap:
        return StopCheck(False, dist, cap, f"Stop is {dist:.1f} away, more than the normal maximum of {cap:.1f}. "
                                           "Too much risk for this setup: skip it (the stop is not widened).")
    return StopCheck(True, dist, cap, f"Stop is {dist:.1f} away, within the normal maximum of {cap:.1f}.")
