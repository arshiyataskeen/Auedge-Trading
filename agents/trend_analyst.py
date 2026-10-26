"""Trend analyst: daily setup from market structure, liquidity sweeps and premium/discount zones.

1. Structure: Daily trend (higher highs/lows or lower highs/lows) and the last break of structure, 4H as confirmation.
2. Liquidity sweep: a wick through recent lows (sell stops taken) or highs (buy stops taken) that closes back.
3. Premium/discount: the daily dealing range (last swing low to swing high). Buys only in discount (lower half),
   sells only in premium (upper half); the best area is the OTE band (62-79% retracement).
4. Entry: in an uptrend, buy in the discount OTE band, ideally after a sell-side sweep; stop beyond the range low;
   target the range high, then the next untouched liquidity. Mirror for downtrends.
"""
from core.indicators import atr
from core.structure import sweep, tf_bias, untouched
from .base import BaseAgent


class TrendAnalystAgent(BaseAgent):
    name, label, weight = "trend", "Trend analyst", 1.5

    async def analyze(self, ctx):
        d, h4, m15 = ctx.struct("1d"), ctx.struct("4h"), ctx.struct("15m")
        if any(cs is None or len(cs.candles) < 60 for cs in (d, h4, m15)):
            return self.insufficient(ctx, "Needs Daily, 4H and 15m candles (60+ each).")
        sp = ctx.sp
        price = m15.candles[-1].c
        da = atr(d.candles)[-1] or 10.0
        db, hb = tf_bias(d.candles, 3), tf_bias(h4.candles, 2.5)
        rows, warnings, levels = [], [], []

        # 1) Market structure
        word = {"UP": "uptrend (higher highs and lows)", "DOWN": "downtrend (lower highs and lows)", "RANGE": "range"}
        trend = 1 if db["state"] == "UP" else -1 if db["state"] == "DOWN" else 0
        if trend == 0 and "BUY" in db["bias"] and "BUY" in hb["bias"]:
            trend = 1
        elif trend == 0 and "SELL" in db["bias"] and "SELL" in hb["bias"]:
            trend = -1
        bos = db["bos"]
        rows.append(["Daily structure", word[db["state"]] +
                     (f", last break {'above' if bos[1] == 'UP' else 'below'} {sp(bos[2]):,.0f}" if bos else "")])
        h4_agrees = trend and (("BUY" in hb["bias"]) if trend > 0 else ("SELL" in hb["bias"]))
        rows.append(["4H structure", f"{word[hb['state']]} · {hb['bias']}" +
                     (" (confirms)" if h4_agrees else " (pulling back)" if trend else "")])

        # 2) Liquidity sweeps (stops just taken)
        sw_d, sw_4 = sweep(d.candles, 20, 5), sweep(h4.candles, 20, 12)
        def sw_text(sw, tf):
            if not sw:
                return None
            kind = "sell stops below" if sw[0] == "spring" else "buy stops above"
            return f"{tf}: {kind} {sp(sw[1]):,.0f} swept, closed back"
        sweeps = [t for t in (sw_text(sw_d, "Daily"), sw_text(sw_4, "4H")) if t]
        rows.append(["Liquidity sweep", "; ".join(sweeps) or "none recently"])
        swept_sell = any(sw and sw[0] == "spring" for sw in (sw_d, sw_4))
        swept_buy = any(sw and sw[0] == "upthrust" for sw in (sw_d, sw_4))

        # 3) Premium / discount on the daily dealing range (latest swing high and low, incl. the forming one)
        piv = db["pivots"]
        hi = next((p.price for p in reversed(piv) if p.kind == "H"), None)
        lo = next((p.price for p in reversed(piv) if p.kind == "L"), None)
        if hi is None or lo is None or hi - lo < da:
            return self.insufficient(ctx, "No clear daily dealing range yet (swing high and low too close).")
        if price > hi:                                          # price broke out: stretch the range to the new extreme
            hi = max(c.h for c in d.candles[-3:])
        if price < lo:
            lo = min(c.l for c in d.candles[-3:])
        rng = hi - lo
        pos = (price - lo) / rng
        eq = lo + rng / 2
        zone = "PREMIUM (expensive)" if pos > 0.5 else "DISCOUNT (cheap)"
        rows.append(["Dealing range", f"{sp(lo):,.0f} – {sp(hi):,.0f} · middle {sp(eq):,.0f}"])
        rows.append(["Price is in", f"{zone}, {pos * 100:.0f}% of the range"])
        levels += [self.level(ctx, d, "band", eq, "Daily equilibrium (50%)")]

        # 4) Daily setup and entry
        bsl, ssl = untouched(d.candles, piv)
        if trend > 0:
            z_lo, z_hi = lo + 0.21 * rng, lo + 0.38 * rng          # discount OTE (62-79% retracement)
            stop, t1 = lo - 0.3 * da, hi
            t2 = next((x for x in bsl if x > hi), hi + 0.5 * rng)
            in_zone, good_side = z_lo <= price <= z_hi, pos <= 0.5
            sweep_ok = swept_sell
        elif trend < 0:
            z_lo, z_hi = hi - 0.38 * rng, hi - 0.21 * rng          # premium OTE
            stop, t1 = hi + 0.3 * da, lo
            t2 = next((x for x in ssl if x < lo), lo - 0.5 * rng)
            in_zone, good_side = z_lo <= price <= z_hi, pos >= 0.5
            sweep_ok = swept_buy
        else:
            rows.append(["Daily setup", f"No trend: buy only near {sp(lo):,.0f} after sell stops are swept, "
                                        f"sell only near {sp(hi):,.0f} after buy stops are swept."])
            return self.result(ctx, bias="WAIT", bias_label="RANGE", confidence=30, subtitle="Daily setup · 4H confirm",
                               headline="Daily range: no trend setup", rows=rows, warnings=warnings, levels=levels,
                               timeframe="1d", summary=f"Daily is ranging between {sp(lo):,.0f} and {sp(hi):,.0f}. "
                               "Wait for a sweep at one edge, or a daily close outside the range.")

        side = "BUY" if trend > 0 else "SELL"
        tword = ("uptrend" if trend > 0 else "downtrend") if db["state"] != "RANGE" else             f"range leaning {'up' if trend > 0 else 'down'} (4H agrees)"
        risk = abs(((z_lo + z_hi) / 2) - stop)
        rows.append(["Daily setup", f"{side} in {'discount' if trend > 0 else 'premium'} zone "
                                    f"{sp(z_lo):,.0f} – {sp(z_hi):,.0f}"])
        rows.append(["Stop / targets", f"stop {sp(stop):,.0f} · T1 {sp(t1):,.0f} · T2 {sp(t2):,.0f} "
                                       f"(T1 ≈ {abs(t1 - (z_lo + z_hi) / 2) / risk:.1f}× risk)"])
        levels += [self.level(ctx, d, "entry", z_lo, f"{side} zone low"), self.level(ctx, d, "entry", z_hi, f"{side} zone high"),
                   self.level(ctx, d, "stop", stop, "Daily setup stop (beyond range)"),
                   self.level(ctx, d, "target", t1, "Target 1 (range extreme)"), self.level(ctx, d, "target", t2, "Target 2")]

        conf = 40 + (10 if h4_agrees else 0) + (15 if sweep_ok else 0) + (15 if in_zone else 0)
        if good_side:
            bias, label = side, f"{side}" + (" (A+)" if in_zone and sweep_ok else "")
            if in_zone:
                summary = (f"Daily {tword} and price is in the "
                           f"{'discount' if trend > 0 else 'premium'} entry zone {sp(z_lo):,.0f}–{sp(z_hi):,.0f}. ")
            else:
                summary = (f"Daily {tword} and price is on the right side "
                           f"({zone.split()[0].lower()}), but not yet in the best zone {sp(z_lo):,.0f}–{sp(z_hi):,.0f}. ")
            summary += ("Liquidity was just swept in our favour. " if sweep_ok else
                        "No sweep yet: wait for stops to be taken and a 15m close back for a cleaner entry. ")
            summary += f"Stop {sp(stop):,.0f}, targets {sp(t1):,.0f} then {sp(t2):,.0f}."
        else:
            bias, label = "WAIT", f"{side} (wait)"
            conf = min(conf, 45)
            summary = (f"Daily {tword}, but price is in "
                       f"{zone.split()[0].lower()}: too {'expensive to buy' if trend > 0 else 'cheap to sell'}. "
                       f"Wait for a pullback into {sp(z_lo):,.0f}–{sp(z_hi):,.0f}, then {side.lower()}.")
            warnings.append(f"Do not chase: {side.lower()}ing in {zone.split()[0].lower()} gives a poor risk/reward.")
        return self.result(ctx, bias=bias, bias_label=label, confidence=min(80, conf), subtitle="Daily setup · 4H confirm",
                           headline=summary.split(".")[0], summary=summary, rows=rows, warnings=warnings,
                           levels=levels, timeframe="1d",
                           metrics={"zone_pos": round(pos * 100), "trend": trend, "swept": "yes" if sweep_ok else "no"})
