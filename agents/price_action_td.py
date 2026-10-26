"""Price action, top-down: daily swing series and candle, 4H key bands and flags, 15m reversal and support."""
from core.indicators import atr, cluster
from core.structure import highs, last_bos, lows, run_count, untouched, zigzag
from .base import BaseAgent


def candle_word(c):
    body, rng = abs(c.c - c.o), (c.h - c.l) or 1e-9
    up_w, lo_w = c.h - max(c.o, c.c), min(c.o, c.c) - c.l
    if up_w >= 2 * body and up_w > lo_w:
        return "shooting star / rejection from above", -1
    if lo_w >= 2 * body and lo_w > up_w:
        return "hammer / rejection from below", 1
    if body < 0.1 * rng:
        return "doji (undecided)", 0
    return ("bullish candle", 1) if c.c > c.o else ("bearish candle", -1)


class PriceActionTDAgent(BaseAgent):
    name, label, weight = "price_action", "Price action", 1.0   # its agreement lost -4.2R in the study

    async def analyze(self, ctx):
        d, h4, m15 = ctx.struct("1d"), ctx.struct("4h"), ctx.struct("15m")
        if any(cs is None or len(cs.candles) < 60 for cs in (d, h4, m15)):
            return self.insufficient(ctx, "Needs Daily, 4H and 15m candles (60+ each).")
        rows, score, levels = [], 0, []
        # Daily
        dp = zigzag(d.candles, 3)
        lh, hl = run_count(highs(dp), lower=True), run_count(lows(dp), lower=False)
        today = d.candles[-1]
        word, cdir = candle_word(today)
        series = f"{lh + 1} lower highs in a row" if lh else f"{hl + 1} higher lows in a row" if hl else "No clear swing series"
        rows.append(["Daily", f"{series}. Today: H {ctx.sp(today.h):,.0f}, now {ctx.sp(today.c):,.0f} ({word})."])
        score += -1 if lh else 1 if hl else 0
        score += 0.5 * cdir
        # 4H key bands
        hp = zigzag(h4.candles, 2.5)
        a4 = atr(h4.candles)[-1]
        price = h4.candles[-1].c
        bsl, ssl = untouched(h4.candles, hp)
        res = sorted(p for p, _ in cluster([x for x in bsl if x > price], 0.6 * a4))
        sup = sorted((p for p, _ in cluster([x for x in ssl if x < price], 0.6 * a4)), reverse=True)
        if not res:
            res = sorted(p.price for p in highs(hp) if p.price > price)
        if not sup:
            sup = sorted((p.price for p in lows(hp) if p.price < price), reverse=True)
        band = f"{ctx.sp(res[0]):,.0f}-{ctx.sp(res[0] + 0.5 * a4):,.0f}" if res else "none above"
        rows.append(["4H", f"Key resistance band {band}" + (f"; support {ctx.sp(sup[0]):,.0f}" if sup else "")])
        h4_lh = run_count(highs(hp), lower=True)
        score += -1 if h4_lh else (1 if run_count(lows(hp), lower=False) else 0)
        # 4H flag: strong leg then a shallow counter channel
        last8, prev = h4.candles[-8:], h4.candles[-20:-8]
        leg = prev[-1].c - prev[0].o
        drift = last8[-1].c - last8[0].o
        pattern = "None clear"
        if leg < -3 * a4 and 0 < drift < 0.5 * -leg:
            pattern = f"Bear flag possible on 4H if {band.split('-')[0]} holds"
            score -= 0.5
        elif leg > 3 * a4 and 0 > drift > -0.5 * leg:
            pattern = "Bull flag possible on 4H"
            score += 0.5
        # 15m
        mp = zigzag(m15.candles, 2)
        bos = last_bos(m15.candles, mp)
        m_sup = lows(mp)[-1].price if lows(mp) else None
        if bos and bos[0] >= len(m15.candles) - 24:
            txt = f"{'V-reversal up' if bos[1] == 'UP' else 'Breakdown'} (break of {ctx.sp(bos[2]):,.0f})."
        else:
            txt = "No fresh break of structure."
        if m_sup:
            txt += f" Support {ctx.sp(m_sup):,.0f}; a close below it = no long trade."
        rows.append(["15m", txt])
        rows.append(["Pattern", pattern])
        flip = highs(dp)[-1].price if lh and highs(dp) else lows(dp)[-1].price if hl and lows(dp) else None
        if flip:
            rows.append(["Flip signal", f"Daily close {'above' if lh else 'below'} {ctx.sp(flip):,.0f} = bias changes"])

        facts = []
        if lh or h4_lh:
            facts.append(" and ".join(x for x, ok in (("Daily", lh), ("4H", h4_lh)) if ok) + " print lower highs")
        if hl:
            facts.append("Daily prints higher lows")
        facts.append(f"today is a {word}")
        fact_txt = "; ".join(facts)
        fact_txt = fact_txt[0].upper() + fact_txt[1:] + ". "
        if score <= -1:
            bias, label = "SELL", "SELL (HTF)"
            summary = fact_txt + (f"Treat {band.split('-')[0]} as a ceiling; " if res else "") +                 "an intraday buy is fine but not a swing trade."
        elif score >= 1:
            bias, label = "BUY", "BUY (HTF)"
            summary = fact_txt + "Buy pullbacks to support; avoid shorting strength."
        else:
            bias, label, summary = "WAIT", "MIXED", "Daily and 4H price action disagree. Trade only the range edges."
        if res:
            levels.append(self.level(ctx, h4, "resistance", res[0], "4H key resistance"))
        if sup:
            levels.append(self.level(ctx, h4, "support", sup[0], "4H support"))
        if m_sup:
            levels.append(self.level(ctx, m15, "support", m_sup, "15m support"))
        metrics = {"score": score}
        if res:
            metrics.update(sell_zone_lo=ctx.sp(res[0]), sell_zone_hi=ctx.sp(res[0] + 0.5 * a4))
        if m_sup:
            metrics["m15_support"] = ctx.sp(m_sup)
        return self.result(ctx, bias=bias, bias_label=label, confidence=min(80, int(35 + 15 * abs(score))),
                           subtitle="Daily + 4H", headline=summary.split(". ")[0], summary=summary, rows=rows,
                           levels=levels, metrics=metrics, timeframe="1d/4h/15m")
