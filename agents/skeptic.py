"""Skeptic: runs after the other agents and argues against the most tempting trade idea."""
from core.structure import highs, lows, sweep, tf_bias, untouched, zigzag
from core.newsintel.mode import NEWS_AGENT

from .base import BaseAgent

NON_VOTING = {NEWS_AGENT}   # display-only agents (votes=False) never count as a stage-1 opinion


class SkepticAgent(BaseAgent):
    name, label, weight = "skeptic", "Skeptic", 0.75
    stage = 2

    async def analyze(self, ctx):
        d, h4, m15 = ctx.struct("1d"), ctx.struct("4h"), ctx.struct("15m")
        prior = [r for r in ctx.prior if r.status == "OK" and r.agent not in NON_VOTING]
        if not prior or any(cs is None or len(cs.candles) < 60 for cs in (d, h4, m15)):
            return self.insufficient(ctx, "Needs the other agents' results and Daily/4H/15m candles.")
        price = m15.candles[-1].c
        ltf = tf_bias(m15.candles, 2)
        htf = tf_bias(h4.candles, 2.5)
        # The "tempting idea" is the short-term direction (what a trader feels like doing now).
        idea = 1 if "BUY" in ltf["bias"] else -1 if "SELL" in ltf["bias"] else \
            (1 if sum(r.bias == "BUY" for r in prior) >= sum(r.bias == "SELL" for r in prior) else -1)
        word = "buy" if idea > 0 else "sell"
        dp = zigzag(d.candles, 3)
        bsl, ssl = untouched(d.candles, dp)
        ssl = [p for p in ssl if p < price]
        bsl = [p for p in bsl if p > price]
        objections = []
        if idea > 0 and ssl:
            objections.append(f"{ctx.sp(ssl[0]):,.0f} is untouched sell-side liquidity. Price may hunt it first.")
        if idea < 0 and bsl:
            objections.append(f"{ctx.sp(bsl[0]):,.0f} is untouched buy-side liquidity. Price may squeeze up to it.")
        if ("SELL" in htf["bias"] and idea > 0) or ("BUY" in htf["bias"] and idea < 0):
            objections.append(f"The 4H trend is against a {word}: it is a counter-trend trade.")
        y = d.candles[-2]
        up_w, lo_w, body = y.h - max(y.o, y.c), min(y.o, y.c) - y.l, abs(y.c - y.o) or 1e-9
        if idea > 0 and up_w > 1.5 * body:
            objections.append(f"Yesterday's daily candle rejected from above (high {ctx.sp(y.h):,.0f}).")
        if idea < 0 and lo_w > 1.5 * body:
            objections.append(f"Yesterday's daily candle rejected from below (low {ctx.sp(y.l):,.0f}).")
        sw = sweep(m15.candles)
        if sw and ((idea > 0 and sw[0] == "upthrust") or (idea < 0 and sw[0] == "spring")):
            objections.append(f"The 15m just printed a {sw[0]} at {ctx.sp(sw[1]):,.0f}, which argues against a {word}.")
        for r in prior:
            if r.agent == "elliott" and r.bias_label == "SPLIT":
                objections.append("The Elliott count is split, so the wave target is not reliable.")
            if r.agent == "macro" and r.metrics.get("weekend") == "yes":
                objections.append("Weekend gap risk: a stop can be jumped over at Monday's open.")
            if r.agent == "macro" and ((idea > 0 and r.bias == "SELL") or (idea < 0 and r.bias == "BUY")):
                objections.append("Macro (dollar) works against this idea.")
        rows = [[f"Objection {i + 1}", o] for i, o in enumerate(objections[:4])]
        m_sup = lows(zigzag(m15.candles, 2))
        m_res = highs(zigzag(m15.candles, 2))
        if idea > 0 and m_sup:
            stop = m_sup[-1].price
            rows.append(["Pre-mortem", f"Buy near {ctx.sp(price):,.0f}, stop under {ctx.sp(stop):,.0f}; a fast drop "
                                       f"{'toward ' + format(ctx.sp(ssl[0]), ',.0f') if ssl else 'through support'} stops it out."])
        elif idea < 0 and m_res:
            stop = m_res[-1].price
            rows.append(["Pre-mortem", f"Sell near {ctx.sp(price):,.0f}, stop above {ctx.sp(stop):,.0f}; a squeeze "
                                       f"{'toward ' + format(ctx.sp(bsl[0]), ',.0f') if bsl else 'through resistance'} stops it out."])
        h4h, h4l = highs(htf["pivots"]), lows(htf["pivots"])
        if idea > 0 and h4h:
            rows.append(["Flip condition", f"4H close and hold above {ctx.sp(h4h[-1].price):,.0f} for 2 candles = Skeptic accepts the buy."])
        elif idea < 0 and h4l:
            rows.append(["Flip condition", f"4H close and hold below {ctx.sp(h4l[-1].price):,.0f} for 2 candles = Skeptic accepts the sell."])

        n = len(objections)
        if n >= 3:
            bias = "SELL" if idea > 0 else "BUY"
            summary = f"{n} serious objections to the {word}. The other side has the better case right now."
        elif n == 2:
            bias = "WAIT"
            summary = f"Two real objections to the {word}. Only take it at a better price with a tight stop."
        else:
            bias = "BUY" if idea > 0 else "SELL"
            summary = f"The Skeptic finds {'no' if n == 0 else 'only one'} serious objection to the {word}."
        return self.result(ctx, bias=bias, confidence=min(75, 30 + 12 * n) if bias != "WAIT" else 30,
                           subtitle=f"Against the {word} idea", headline=summary.split(".")[0], summary=summary,
                           rows=rows, timeframe="1d/4h/15m", metrics={"objections": n, "idea": word})
