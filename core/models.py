"""Shared data shapes used by the data layer, every agent and the Chief."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Status = Literal["OK", "ERROR", "INSUFFICIENT_DATA"]
Bias = Literal["BUY", "SELL", "WAIT"]


class Level(BaseModel):
    kind: str            # support | resistance | entry | stop | target | pivot | band
    price: float
    note: str = ""


class AgentResult(BaseModel):
    agent: str
    status: Status = "OK"
    bias: Bias = "WAIT"
    confidence: int = Field(0, ge=0, le=100)
    headline: str = ""
    reasons: list[str] = []
    warnings: list[str] = []
    levels: list[Level] = []
    timeframe: str = ""
    # Extras (not part of the voting): a risk veto and numbers other agents/Chief may use.
    veto: bool = False
    metrics: dict[str, float | str] = {}
    # Display helpers for the panel
    subtitle: str = ""                    # e.g. "Daily + 4H"
    bias_label: str = ""                  # e.g. "SELL (HTF)", "SPLIT"; defaults to bias
    rows: list[list[str]] = []            # [label, value] table rows
    summary: str = ""                    # one plain-language paragraph


class Candle(BaseModel):
    t: int               # candle start, unix seconds (UTC)
    o: float
    h: float
    l: float
    c: float
    v: float = 0


class CandleSet(BaseModel):
    key: str             # e.g. "spot_15m", "fut_1h"
    timeframe: str       # "5m" | "15m" | "1h" | "4h"
    kind: Literal["spot", "futures"]
    source_label: str    # shown in the UI
    candles: list[Candle] = []
    last_is_forming: bool = True   # newest candle not finished yet

    def closed(self) -> list[Candle]:
        return self.candles[:-1] if self.last_is_forming and self.candles else list(self.candles)


class DailyBar(BaseModel):
    d: str               # YYYY-MM-DD
    c: float
    h: float
    l: float             # no open price in XAUS history


class SpotQuote(BaseModel):
    price: float
    updated_at: datetime
    age_seconds: float   # computed by us: now - updated_at
    stale: bool          # computed by us, never taken from data_state
    price_source: str
    api_data_state: dict = {}


class MarketContext(BaseModel):
    generated_at: datetime
    analysis_tf: str
    spot: Optional[SpotQuote] = None
    candles: dict[str, CandleSet] = {}
    daily: list[DailyBar] = []            # futures (Yahoo GC=F) daily bars
    daily_source: str = ""
    futures_last: Optional[float] = None  # latest futures 1m close
    futures_last_age_s: Optional[float] = None
    futures_gap: Optional[float] = None   # futures - spot (approx, futures are delayed)
    intraday_coverage_s: Optional[int] = None
    intraday_interval_s: Optional[int] = None   # spot sampling interval (was 120, now 300)
    markets: dict[str, list[Candle]] = {}       # other assets: dxy_1h, silver_1h, sp500_1d
    prior: list[AgentResult] = []               # stage-1 results, given to stage-2 agents (Skeptic)
    cot: list[dict] = []                        # weekly CFTC positioning rows (core/cot.py), filtered by publish time

    def struct(self, tf: str) -> Optional[CandleSet]:
        """Real-OHLC candles for structure analysis (futures, levels converted to spot by agents)."""
        return self.candles.get(f"fut_{tf}")

    def sp(self, futures_price: Optional[float]) -> Optional[float]:
        """Convert a futures price to an approximate spot price using the live gap."""
        if futures_price is None:
            return None
        return round(futures_price - (self.futures_gap or 0), 2)
    errors: list[str] = []

    def pick(self, tf: str, min_bars: int) -> tuple[Optional[CandleSet], list[str]]:
        """Spot candles for `tf` if there are enough closed bars, else futures candles (flagged)."""
        notes: list[str] = []
        spot = self.candles.get(f"spot_{tf}")
        if spot and len(spot.closed()) >= min_bars:
            return spot, notes
        fut = self.candles.get(f"fut_{tf}")
        if fut and len(fut.closed()) >= min_bars:
            notes.append(f"No usable spot candles for {tf}; used gold FUTURES candles for direction "
                         f"(futures run above spot, so their price levels are not spot levels).")
            return fut, notes
        return None, notes
