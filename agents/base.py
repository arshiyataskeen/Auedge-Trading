"""Base class and safe runner shared by every agent."""
from __future__ import annotations

import asyncio
import traceback

from core.models import AgentResult, CandleSet, Level, MarketContext

AGENT_TIMEOUT_S = 10


class BaseAgent:
    name = "base"          # id used in results
    label = "Base"         # name shown in the UI
    weight = 1.0           # how much the Chief listens to this agent
    votes = True           # False = never counted as bullish/bearish (e.g. the risk guard)

    async def analyze(self, ctx: MarketContext) -> AgentResult:  # pragma: no cover
        raise NotImplementedError

    # ---- helpers for subclasses ----
    def result(self, ctx: MarketContext, **kw) -> AgentResult:
        kw.setdefault("timeframe", ctx.analysis_tf)
        kw["levels"] = [lv for lv in kw.get("levels", []) if lv is not None]
        return AgentResult(agent=self.name, **kw)

    def insufficient(self, ctx: MarketContext, why: str, notes: list[str] | None = None) -> AgentResult:
        return self.result(ctx, status="INSUFFICIENT_DATA", bias="WAIT", confidence=0,
                           headline="Not enough data", reasons=[why], warnings=notes or [])

    @staticmethod
    def level(ctx: MarketContext, cs: CandleSet | None, kind: str, price: float | None, note: str = "") -> Level | None:
        """Make a spot-price level. Futures prices are shifted by the futures−spot gap."""
        if price is None:
            return None
        if cs is not None and cs.kind == "futures":
            if ctx.futures_gap is None:
                return None
            price -= ctx.futures_gap
            note = (note + " " if note else "") + "(≈ spot, converted from futures)"
        return Level(kind=kind, price=round(price, 2), note=note)


async def run_agent(agent: BaseAgent, ctx: MarketContext) -> AgentResult:
    """Run one agent; any crash or timeout becomes an ERROR result instead of breaking the pipeline."""
    try:
        return await asyncio.wait_for(agent.analyze(ctx), timeout=AGENT_TIMEOUT_S)
    except asyncio.TimeoutError:
        return AgentResult(agent=agent.name, status="ERROR", bias="WAIT", confidence=0,
                           headline="Timed out", reasons=[f"Took longer than {AGENT_TIMEOUT_S}s"],
                           timeframe=ctx.analysis_tf)
    except Exception as e:  # noqa: BLE001 - isolation is the point
        traceback.print_exc()
        return AgentResult(agent=agent.name, status="ERROR", bias="WAIT", confidence=0,
                           headline="Agent error", reasons=[f"{type(e).__name__}: {e}"],
                           timeframe=ctx.analysis_tf)
