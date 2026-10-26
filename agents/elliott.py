"""Elliott: approximate wave count. Daily ABC projections + 15m micro impulse. Counts are subjective."""
from core.indicators import atr
from core.structure import confirmed, zigzag
from .base import BaseAgent


class ElliottAgent(BaseAgent):
    name, label, weight = "elliott", "Elliott", 1.0

    async def analyze(self, ctx):
        d, m = ctx.struct("1d"), ctx.struct("15m")
        if not d or not m or len(d.candles) < 120 or len(m.candles) < 60:
            return self.insufficient(ctx, "Needs about 6 months of daily and 2 days of 15m candles.")
        price_f = d.candles[-1].c                      # futures price (structure is in futures)
        da = atr(d.candles)[-1]
        pv = confirmed(zigzag(d.candles, 3))
        rows, warnings = [], ["Elliott counts are subjective; this is one possible count, not a fact."]
        macro_dir, levels = 0, []
        if len(pv) >= 3:
            p0, p1, p2 = pv[-3], pv[-2], pv[-1]
            a_len = p0.price - p1.price                     # >0 means A went down
            b_ret = abs(p2.price - p1.price) / abs(a_len) if a_len else 0
            if b_ret < 1:
                sign = 1 if a_len > 0 else -1               # 1: A down, C expected down
                macro_dir = -sign
                c_moving = (price_f < p2.price) if sign > 0 else (price_f > p2.price)
                rows.append(["Daily structure", f"A: {ctx.sp(p0.price):,.0f}→{ctx.sp(p1.price):,.0f} · "
                                                f"B: {ctx.sp(p1.price):,.0f}→{ctx.sp(p2.price):,.0f} · "
                                                f"C {'in progress' if c_moving else 'not started'}"])
                for k in (0.5, 0.618, 1.0):
                    lvl = p2.price - sign * k * abs(a_len)
                    gone = (price_f <= lvl) if sign > 0 else (price_f >= lvl)
                    near = abs(price_f - lvl) <= da
                    tag = "← price is here" if near else "← reached" if gone else "← if C extends"
                    rows.append([f"C = {k:g}×A", f"{ctx.sp(lvl):,.0f} {tag}"])
                    levels.append(self.level(ctx, d, "target", lvl, f"Elliott C = {k:g}×A"))
            else:
                macro_dir = 1 if p2.price > p0.price else -1
                rows.append(["Daily structure", f"Swing from {ctx.sp(p1.price):,.0f} retraced over 100%: "
                                                f"new {'up' if macro_dir > 0 else 'down'}trend count"])
        else:
            rows.append(["Daily structure", "Not enough daily swings for a count"])

        mp = confirmed(zigzag(m.candles, 2))
        micro_dir, m_price = 0, m.candles[-1].c
        if len(mp) >= 3:
            a, b, c = mp[-3], mp[-2], mp[-1]
            if a.kind == "L" and c.kind == "L" and c.price > a.price and m_price > c.price:
                w3 = c.price + 1.618 * (b.price - a.price)
                micro_dir = 1
                rows.append(["15m micro", f"Wave 1: {ctx.sp(a.price):,.0f}→{ctx.sp(b.price):,.0f} · "
                                          f"Wave 2: pullback to {ctx.sp(c.price):,.0f} · Wave 3: ~{ctx.sp(w3):,.0f}"])
                levels.append(self.level(ctx, m, "target", w3, "Elliott micro wave 3"))
            elif a.kind == "H" and c.kind == "H" and c.price < a.price and m_price < c.price:
                w3 = c.price - 1.618 * (a.price - b.price)
                micro_dir = -1
                rows.append(["15m micro", f"Wave 1: {ctx.sp(a.price):,.0f}→{ctx.sp(b.price):,.0f} · "
                                          f"Wave 2: bounce to {ctx.sp(c.price):,.0f} · Wave 3: ~{ctx.sp(w3):,.0f}"])
                levels.append(self.level(ctx, m, "target", w3, "Elliott micro wave 3"))
            else:
                rows.append(["15m micro", "Corrective / unclear micro structure"])
        recent_low = min(c.l for c in m.candles[-96:])
        recent_high = max(c.h for c in m.candles[-96:])
        if macro_dir < 0:
            rows.append(["Key question", f"Is {ctx.sp(recent_low):,.0f} the end of C or an interim low?"])
        elif macro_dir > 0:
            rows.append(["Key question", f"Is {ctx.sp(recent_high):,.0f} the end of the move or an interim high?"])

        if macro_dir and micro_dir and macro_dir != micro_dir:
            bias, label, conf = "WAIT", "SPLIT", 30
            summary = ("Elliott is split: the daily count points one way, the 15m micro count the other. "
                       "Wait until the micro count completes or fails.")
        elif macro_dir:
            bias = "BUY" if macro_dir > 0 else "SELL"
            label, conf = bias, 50 + (15 if micro_dir == macro_dir else 0)
            summary = f"Daily count favours {'upside' if macro_dir > 0 else 'downside'}" + (
                " and the 15m micro count agrees." if micro_dir == macro_dir else "; the 15m is not clear yet.")
        else:
            bias, label, conf, summary = "WAIT", "UNCLEAR", 20, "No reliable count right now."
        return self.result(ctx, bias=bias, bias_label=label, confidence=conf, subtitle="Full top-down",
                           headline=summary.split(":")[0], summary=summary, rows=rows, warnings=warnings,
                           levels=levels, timeframe="1d/15m", metrics={"macro_dir": macro_dir, "micro_dir": micro_dir})
