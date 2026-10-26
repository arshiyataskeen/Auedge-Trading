"""Stop-hunt agent: where traders' stop losses are resting, which pool is likely to be swept next, and what a
fresh sweep means. Built on the stop-loss map (core/liquidity.py).

- Votes only on the classic reversal: a pool of stops was just swept (wick through, no close beyond) and price is
  back on the other side. Sell stops taken below -> trapped sellers and filled big buyers -> BUY; mirror for SELL.
- Otherwise it says which pool is the nearest "magnet" (strong and close) and does not vote: entering in front of
  a pool that is likely to be swept is how retail stops get taken.
- It also suggests stop placement beyond the obvious pools instead of right at them.
"""
from core.liquidity import build_stop_map
from .base import BaseAgent

MAGNET_RANGE_ATR = 3.0      # only pools within 3x the 1H ATR count as near
FRESH_MIN = 120             # a sweep in the last 2 hours is a live setup (the map keeps 4 hours)


def magnet(pool, price, a1) -> float:
    return pool.strength / max(0.3, abs(pool.price - price) / a1)


class StopHuntAgent(BaseAgent):
    name, label, weight = "stophunt", "Stop-hunt", 1.0

    async def analyze(self, ctx):
        m = build_stop_map(ctx)
        if m["price"] is None or not m["atr1h"]:
            return self.insufficient(ctx, "Needs Daily, 4H, 1H and 15m candles for the stop-loss map.")
        p, a1 = m["price"], m["atr1h"]
        above = [x for x in m["above"] if x.status == "untouched" and abs(x.price - p) <= MAGNET_RANGE_ATR * a1]
        below = [x for x in m["below"] if x.status == "untouched" and abs(x.price - p) <= MAGNET_RANGE_ATR * a1]
        rows, levels, warnings = [], [], []
        pl = lambda xs: " · ".join(f"{x.price:,.0f} (strength {x.strength:g})" for x in xs[:2]) or "none near"
        rows.append(["Buy stops above", pl(above)])
        rows.append(["Sell stops below", pl(below)])

        hunt = m["recent_hunt"]
        bias, conf, label, summary = "WAIT", 30, "NO SWEEP", ""
        if hunt and hunt.hunted_ago_min is not None and hunt.hunted_ago_min <= FRESH_MIN:
            side = "BUY" if hunt.side == "sell" else "SELL"
            conf = 60 if hunt.strength >= 2 else 50
            bias, label = side, f"SWEPT {'BELOW' if side == 'BUY' else 'ABOVE'} · {side}"
            summary = (f"{'Sell' if side == 'BUY' else 'Buy'} stops at {hunt.price:,.0f} were swept "
                       f"{hunt.hunted_ago_min} min ago and price is back {'above' if side == 'BUY' else 'below'} them: "
                       f"the stopped-out traders' orders were the fuel for a move {'up' if side == 'BUY' else 'down'}.")
            rows.append(["Fresh sweep", f"{hunt.price:,.0f} ({', '.join(hunt.sources)}) · {hunt.hunted_ago_min} min ago"])
            levels.append(self.level(ctx, None, "pivot", hunt.price, "Swept stop pool (reversal level)"))
        elif hunt:
            rows.append(["Last sweep", f"{hunt.price:,.0f} · {hunt.hunted_ago_min} min ago (older than {FRESH_MIN} min)"])

        # Next likely hunt: the stronger magnet (strength / distance)
        cand = [(magnet(x, p, a1), x, "above") for x in above[:1]] + [(magnet(x, p, a1), x, "below") for x in below[:1]]
        cand.sort(key=lambda c: -c[0])
        if cand:
            score, nxt, where = cand[0]
            other = cand[1][0] if len(cand) > 1 else 0
            clear = score >= 1.8 * other
            rows.append(["Next likely sweep", f"{where} at {nxt.price:,.0f} ({abs(nxt.price - p) / a1:.1f} ATR away)"
                                              + ("" if clear else " · both sides similar")])
            levels.append(self.level(ctx, None, "target", nxt.price, f"Likely stop hunt ({where})"))
            if bias == "WAIT":
                label = f"NEXT: {where.upper()} {nxt.price:,.0f}"
                summary = (f"No fresh sweep. The nearest strong pool is {where} at {nxt.price:,.0f}: price often runs "
                           f"there to take those stops first. Avoid entering just in front of it.")
            if clear and abs(nxt.price - p) < 0.6 * a1:
                warnings.append(f"Price is close to the {where} stops at {nxt.price:,.0f}: a quick spike through them "
                                f"is likely before any real move.")
        if not summary:
            summary = "No stop pools near price and no fresh sweep."

        # Safer stops: beyond the obvious pool, not on it
        if below:
            safe_long = below[0].price - 0.3 * a1
            rows.append(["Safer long stop", f"below {safe_long:,.0f} (past the sell stops at {below[0].price:,.0f})"])
        if above:
            safe_short = above[0].price + 0.3 * a1
            rows.append(["Safer short stop", f"above {safe_short:,.0f} (past the buy stops at {above[0].price:,.0f})"])
        return self.result(ctx, bias=bias, bias_label=label, confidence=conf, headline=summary.split(":")[0],
                           summary=summary, rows=rows, warnings=warnings, levels=levels, timeframe="liquidity",
                           subtitle="Stop-loss pools · sweeps", metrics={"fresh": "yes" if bias != "WAIT" else "no"})
