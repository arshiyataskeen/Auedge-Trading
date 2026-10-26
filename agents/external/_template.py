"""TEMPLATE adapter (ignored because the file name starts with "_").

To plug in an outside agent:
1. Copy this file to agents/external/<agent_name>.py
2. Import the outside code and translate its output into an AgentResult below.
   Keep the outside agent's own logic untouched; only convert inputs and outputs here.
3. Restart the dashboard. It appears in the panel and the Chief counts it with `weight`.
"""
from agents.base import BaseAgent


class ExternalAdapter(BaseAgent):
    name = "external_example"
    label = "External agent (example)"
    weight = 1.0

    async def analyze(self, ctx):
        # Example: candles = [c.model_dump() for c in ctx.candles["spot_15m"].closed()]
        #          raw = outside_module.run(candles)          # the original logic, unchanged
        #          bias = {"long": "BUY", "short": "SELL"}.get(raw["signal"], "WAIT")
        return self.insufficient(ctx, "Template only: no outside agent connected yet.")


AGENT = ExternalAdapter()
