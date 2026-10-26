"""Agent registry: the 6 analysis agents, plus any adapters found in agents/external/.

Stage 1 agents run in parallel; stage 2 (the Skeptic) runs after them and sees their results.
The risk guard is not a voting agent: it is the Chief's data check (stale price, market closed).
"""
import importlib
import pkgutil

from .base import BaseAgent
from .elliott import ElliottAgent
from .market_psych import MarketPsychAgent
from .price_action_td import PriceActionTDAgent
from .psychology import PsychologyAgent
from .risk_guard import RiskGuardAgent
from .session_macro import SessionMacroAgent
from .skeptic import SkepticAgent
from .smart_money import SmartMoneyAgent
from .stop_hunt import StopHuntAgent
from .trend_analyst import TrendAnalystAgent
from .wyckoff import WyckoffAgent

BUILT_IN: list[BaseAgent] = [
    WyckoffAgent(), ElliottAgent(), SmartMoneyAgent(), PriceActionTDAgent(), TrendAnalystAgent(), SessionMacroAgent(), MarketPsychAgent(),
    StopHuntAgent(),
    SkepticAgent(),
]
DATA_CHECK = RiskGuardAgent()
PSYCH = PsychologyAgent()      # discipline guard: runs after the Chief, can cancel a new trade (not used by the backtest)


def load_external() -> tuple[list[BaseAgent], list[str]]:
    """Import every agents/external/<name>.py (not starting with _) that defines AGENT."""
    from . import external
    found, problems = [], []
    for mod in pkgutil.iter_modules(external.__path__):
        if mod.name.startswith("_"):
            continue
        try:
            m = importlib.import_module(f"{external.__name__}.{mod.name}")
            if isinstance(getattr(m, "AGENT", None), BaseAgent):
                found.append(m.AGENT)
            else:
                problems.append(f"{mod.name}: no AGENT object")
        except Exception as e:  # noqa: BLE001 - a broken adapter must not stop the app
            problems.append(f"{mod.name}: {type(e).__name__}: {e}")
    return found, problems


def all_agents() -> tuple[list[BaseAgent], list[str]]:
    ext, problems = load_external()
    return BUILT_IN + ext, problems
