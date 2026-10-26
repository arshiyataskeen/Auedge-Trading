"""Record once: replay every hourly step of the ~6 months with the current agents and Chief (no look-ahead)
and save what each one said, so rule changes can be tested offline without re-running the agents.

Run: .venv\\Scripts\\python.exe research\\record.py      -> data/research/steps_6m.pkl
"""
import asyncio
import pickle
import sys
import time
from bisect import bisect_left
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import backtest as bt  # noqa: E402
from core.indicators import atr  # noqa: E402

OUT = ROOT / "data" / "research" / "steps_6m.pkl"


async def main():
    hist = bt.History(bt.load_data(False, True))
    start15 = (hist.m15[0].t + bt.WINDOW["15m"] + 3599) // 3600 * 3600
    end15 = hist.m15[-1].t + 900
    ex = [(c, 3600) for c in hist.h1 if c.t + 3600 <= start15] + [(c, 900) for c in hist.m15 if c.t >= start15]
    first_T = hist.h1[0].t + bt.HOURLY_WARMUP_S
    steps, started = [], time.time()
    for n, (c, sec) in enumerate(ex):
        T = c.t + sec
        if T % 3600 or T < first_T or n + 1 >= len(ex) or bisect_left(hist.t1h, T) == 0:
            continue
        real15 = start15 <= T <= end15
        ctx = bt.context_hourly(hist, T, real15)
        results, rep = await bt.analyse(ctx)
        h1w = ctx.candles["fut_1h"].candles
        plan = rep.plan
        steps.append({
            "T": T, "n": n, "price": c.c, "real15": real15,
            "atr1h": (atr(h1w)[-1] or 0) if len(h1w) > 20 else 0,
            "agents": {r.agent: {"status": r.status, "bias": r.bias, "conf": r.confidence,
                                 "label": r.bias_label, "metrics": dict(r.metrics)} for r in results},
            "score": rep.weighted_score, "conf": rep.confidence, "bias": rep.bias,
            "tfs": {t.tf: t.bias for t in rep.timeframes},
            "veto": rep.headline.startswith("NO TRADE: data check"),
            "plan": {"kind": plan.kind, "side": plan.side, "entry_lo": plan.entry_lo, "entry_hi": plan.entry_hi,
                     "stop": plan.stop, "t1": plan.t1, "t2": plan.t2},
            "hunt": (rep.recent_hunt.side if rep.recent_hunt else None),
            "pools_above": [p.price for p in rep.stops_above if p.status == "untouched"][:4],
            "pools_below": [p.price for p in rep.stops_below if p.status == "untouched"][:4],
        })
        if len(steps) % 100 == 0:
            el = time.time() - started
            print(f"{len(steps)} steps, {el:.0f}s, at {bt.when(T)}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("wb") as f:
        pickle.dump({"steps": steps, "ex": [(c.t, c.o, c.h, c.l, c.c, s) for c, s in ex], "start15": start15}, f)
    print(f"done: {len(steps)} steps in {time.time() - started:.0f}s -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
