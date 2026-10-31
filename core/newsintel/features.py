"""Features known just before a release at time t, used to explain how gold reacts to it.

Candles are read only through bars.resample / session_day_candles / window, which return
finished candles up to t, so nothing here depends on data from the release itself.
trend_score is the Chief agent's multi-timeframe trend formula applied to those candles.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agents.chief import TFS
from core.indicators import atr
from core.newsintel.bars import NY, resample, session_day_candles, window
from core.newsintel.minutes import Minutes
from core.structure import tf_bias

MIN_CANDLES = 60   # a timeframe needs this many candles to vote (same as the Chief)
N_TREND = 120      # candles requested per timeframe for the trend score
_SECONDS = {"4h": 14400, "1h": 3600, "15m": 900}


@dataclass
class Features:
    t: int
    atr15: float | None
    atr1h: float | None
    pre_range: float | None
    trend_score: float | None
    hours_since_prev: float | None
    overlap: int


def _atr(m: Minutes, sec: int, t: int) -> float | None:
    cs = resample(m, sec, t, 60)
    return atr(cs, 14)[-1] if cs else None


def _trend_score(m: Minutes, t: int) -> float | None:
    total, used = 0.0, False
    for key, _name, mult, w in TFS:
        cs = session_day_candles(m, t, N_TREND) if key == "1d" else resample(m, _SECONDS[key], t, N_TREND)
        if len(cs) < MIN_CANDLES:
            continue
        norm = max(-1.0, min(1.0, tf_bias(cs, mult)["score"] / 2.5))
        total += w * norm
        used = True
    return total if used else None


def features(m: Minutes, t: int, prev_t: int | None) -> Features:
    """Pre-event features at release time t; prev_t is the previous release (any), if known."""
    s = window(m, t - 3600, t)
    pre_range = float(m.h[s].max() - m.l[s].min()) if s.stop > s.start else None
    hour = datetime.fromtimestamp(t, NY).hour
    return Features(
        t=t,
        atr15=_atr(m, 900, t),
        atr1h=_atr(m, 3600, t),
        pre_range=pre_range,
        trend_score=_trend_score(m, t),
        hours_since_prev=None if prev_t is None else (t - prev_t) / 3600,
        overlap=int(8 <= hour <= 11),
    )
