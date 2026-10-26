"""Smart money (SMC): liquidity (BSL/SSL), draw on liquidity, dealing range, OTE, FVGs, A+ checklist."""
from core.structure import fvgs, highs, last_bos, lows, sweep, tf_bias, untouched, zigzag
from .base import BaseAgent


def fmt_list(ctx, prices, n=3):
    return ", then ".join(f"{ctx.sp(p):,.0f}" for p in prices[:n]) or "none nearby"


class SmartMoneyAgent(BaseAgent):
    name, label, weight = "smc", "Smart money", 1.5

    async def analyze(self, ctx):
        d, h4, m15 = ctx.struct("1d"), ctx.struct("4h"), ctx.struct("15m")
        if any(cs is None or len(cs.candles) < 60 for cs in (d, h4, m15)):
            return self.insufficient(ctx, "Needs Daily, 4H and 15m candles (60+ each).")
        price = m15.candles[-1].c
        db, hb, mb = tf_bias(d.candles, 3), tf_bias(h4.candles, 2.5), tf_bias(m15.candles, 2)
        _, d_ssl = untouched(d.candles, db["pivots"])
        d_bsl, _ = untouched(d.candles, db["pivots"])
        h_bsl, h_ssl = untouched(h4.candles, hb["pivots"])
        d_ssl = [p for p in d_ssl if p < price]
        h_bsl = [p for p in h_bsl if p > price]
        h_ssl = [p for p in h_ssl if p < price]

        # 15m dealing range: last swing low and high
        mp = zigzag(m15.candles, 2)
        sh, sl = highs(mp), lows(mp)
        bos = last_bos(m15.candles, mp)
        rows = [["Daily SSL", (fmt_list(ctx, d_ssl, 2) + " (untouched)") if d_ssl else "none below"],
                ["4H BSL", fmt_list(ctx, h_bsl)]]
        htf_dir = (1 if "BUY" in db["bias"] else -1 if "SELL" in db["bias"] else 0) + \
                  (1 if "BUY" in hb["bias"] else -1 if "SELL" in hb["bias"] else 0)
        draw = (d_ssl or h_ssl)[:1] if htf_dir < 0 else h_bsl[:1] if htf_dir > 0 else []
        rows.insert(1, ["4H draw", f"Price heading to {ctx.sp(draw[0]):,.0f} unless 4H structure flips" if draw
                        else "No clear draw on liquidity"])
        metrics = {}
        ote_txt, in_ote, discount, premium = "No clean 15m dealing range", False, False, False
        if sh and sl:
            hi, lo = sh[-1].price, sl[-1].price
            if hi > lo:
                mid = (hi + lo) / 2
                discount, premium = price < mid, price > mid
                if bos and bos[1] == "UP":            # bullish leg: OTE is a 62-79% pullback from the high
                    z_hi, z_lo = hi - 0.62 * (hi - lo), hi - 0.79 * (hi - lo)
                    side = "long"
                else:                                  # bearish leg: OTE is a 62-79% bounce from the low
                    z_lo, z_hi = lo + 0.62 * (hi - lo), lo + 0.79 * (hi - lo)
                    side = "short"
                in_ote = z_lo <= price <= z_hi
                ote_txt = f"{ctx.sp(z_lo):,.0f}-{ctx.sp(z_hi):,.0f} ({side} OTE; price is in {'discount' if discount else 'premium'})"
                metrics[f"ote_{side}_lo"], metrics[f"ote_{side}_hi"] = ctx.sp(z_lo), ctx.sp(z_hi)
        rows.append(["15m OTE", ote_txt])

        gaps = fvgs(m15.candles)
        bull_fvg = any(k == "bull" and top < price and price - top < (price * 0.003) for k, _, top in gaps)
        bear_fvg = any(k == "bear" and bot > price and bot - price < (price * 0.003) for k, bot, _ in gaps)
        sw = sweep(m15.candles)
        long_checks = ["BUY" in db["bias"], "BUY" in hb["bias"], bool(bos and bos[1] == "UP"), discount,
                       in_ote and metrics.get("ote_long_lo") is not None, bull_fvg, bool(sw and sw[0] == "spring")]
        short_checks = ["SELL" in db["bias"], "SELL" in hb["bias"], bool(bos and bos[1] == "DOWN"), premium,
                        in_ote and metrics.get("ote_short_lo") is not None, bear_fvg, bool(sw and sw[0] == "upthrust")]
        ls, ss = sum(long_checks), sum(short_checks)
        rows += [["A+ long score (15m)", f"{ls}/7 now"], ["A+ short score", f"{ss}/7 now"]]
        if h_bsl:
            metrics.update(sell_zone_lo=ctx.sp(h_bsl[0]), sell_zone_hi=ctx.sp(h_bsl[1] if len(h_bsl) > 1 else h_bsl[0] + 20))
        metrics.update(long_score=ls, short_score=ss)

        if htf_dir < 0:
            bias, label = "SELL", "SELL (HTF)"
            summary = (f"The higher-timeframe draw is down toward {ctx.sp(draw[0]):,.0f}. " if draw else "Higher timeframes lean down. ") + \
                      ("A 15m buy is a bounce inside a bearish structure: take it only at the OTE and do not hold it. " if bos and bos[1] == "UP" else "") + \
                      (f"Best short: rejection at {ctx.sp(h_bsl[0]):,.0f} with 4H confirmation." if h_bsl else "")
        elif htf_dir > 0:
            bias, label = "BUY", "BUY (HTF)"
            summary = (f"The higher-timeframe draw is up toward {ctx.sp(draw[0]):,.0f}. " if draw else "Higher timeframes lean up. ") + \
                      "Best long: a pullback into the 15m OTE / discount."
        else:
            bias, label, summary = "WAIT", "NEUTRAL", "Daily and 4H disagree; liquidity on both sides. Wait for a sweep."
        conf = 40 + 6 * max(ls, ss) if bias != "WAIT" else 25
        levels = [self.level(ctx, h4, "resistance", p, "4H buy-side liquidity") for p in h_bsl[:2]] + \
                 [self.level(ctx, d, "support", p, "Daily sell-side liquidity") for p in d_ssl[:1]]
        return self.result(ctx, bias=bias, bias_label=label, confidence=min(conf, 80), subtitle="Top-down",
                           headline=summary.split(". ")[0], summary=summary, rows=rows, metrics=metrics,
                           levels=levels, timeframe="1d/4h/15m")
