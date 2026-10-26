"""Wyckoff: market phase on Daily, 4H and 15m (markdown / markup / accumulation / distribution)."""
from core.indicators import atr
from core.structure import highs, lows, sweep, trend_state, untouched, zigzag
from .base import BaseAgent


class WyckoffAgent(BaseAgent):
    name, label, weight = "wyckoff", "Wyckoff", 0.75      # 48% in the 6-month study (weakest)

    def phase(self, ctx, cs, mult):
        cl = cs.candles
        piv = zigzag(cl, mult)
        state = trend_state(piv)
        a = atr(cl)[-1] or 1
        sw = sweep(cl)
        h, l = highs(piv), lows(piv)
        out = {"state": state, "sweep": sw, "dir": 0, "lps": None, "flip": None}
        if sw and sw[0] == "spring":
            lvl, j = sw[1], sw[2]
            sos = max(c.h for c in cl[max(0, j - 10):j])           # top of the range before the spring
            if any(c.c > sos for c in cl[j + 1:]):
                out.update(text=f"Spring {ctx.sp(lvl):,.0f} → SOS → LPS zone {ctx.sp(sos - 0.5 * a):,.0f}-{ctx.sp(sos):,.0f}",
                           dir=1, lps=(sos - 0.5 * a, sos))
            else:
                out.update(text=f"Spring at {ctx.sp(lvl):,.0f}; waiting for a sign of strength above {ctx.sp(sos):,.0f}",
                           dir=0.5)
        elif sw and sw[0] == "upthrust":
            lvl, j = sw[1], sw[2]
            sow = min(c.l for c in cl[max(0, j - 10):j])
            if any(c.c < sow for c in cl[j + 1:]):
                out.update(text=f"Upthrust {ctx.sp(lvl):,.0f} → SOW → LPSY zone {ctx.sp(sow):,.0f}-{ctx.sp(sow + 0.5 * a):,.0f}",
                           dir=-1)
            else:
                out.update(text=f"Upthrust at {ctx.sp(lvl):,.0f}; waiting for weakness below {ctx.sp(sow):,.0f}", dir=-0.5)
        elif state == "DOWN":
            top = max(h, key=lambda p: p.price).price if h else cl[-1].h
            lh = h[-1].price if h else None
            out.update(text=f"Markdown from {ctx.sp(top):,.0f}" + (f"; lower high at {ctx.sp(lh):,.0f}" if lh else ""),
                       dir=-1, flip=lh)
        elif state == "UP":
            hl = l[-1].price if l else None
            out.update(text="Markup: higher highs and higher lows" + (f"; last higher low {ctx.sp(hl):,.0f}" if hl else ""),
                       dir=1, flip=hl)
        else:
            lo, hi = min(c.l for c in cl[-40:]), max(c.h for c in cl[-40:])
            out.update(text=f"Trading range {ctx.sp(lo):,.0f}-{ctx.sp(hi):,.0f} (accumulation or distribution not yet clear)")
        out["piv"] = piv
        return out

    async def analyze(self, ctx):
        sets = {tf: ctx.struct(tf) for tf in ("1d", "4h", "15m")}
        if any(cs is None or len(cs.candles) < 60 for cs in sets.values()):
            return self.insufficient(ctx, "Needs Daily, 4H and 15m candles (60+ each).")
        d, h4, m15 = (self.phase(ctx, sets["1d"], 3), self.phase(ctx, sets["4h"], 2.5), self.phase(ctx, sets["15m"], 2))
        springs = all(abs(x["dir"]) == 0.5 for x in (d, h4))   # only unconfirmed springs/upthrusts on HTF
        htf = d["dir"] + h4["dir"]
        bsl, ssl = untouched(sets["4h"].candles, h4["piv"])
        _, dssl = untouched(sets["1d"].candles, d["piv"])
        target = (dssl[0] if dssl else ssl[0] if ssl else None) if htf < 0 else (bsl[0] if bsl else None)
        flip = h4["flip"]
        if htf <= -1:
            bias, label, conf = "SELL", "SELL (HTF)", (40 if springs else 55) + (10 if m15["dir"] <= 0 else 0)
            summary = ("Upthrusts on the higher timeframes hint at distribution; a sign of weakness is still needed. "
                       if springs else "The higher timeframes are in markdown. ") + (
                "The 15m shows a spring, but it needs a 4H higher high to confirm real accumulation, "
                "not just a bounce inside distribution." if m15["dir"] > 0 else "The 15m shows no accumulation signs.")
        elif htf >= 1:
            bias, label, conf = "BUY", "BUY (HTF)", (40 if springs else 55) + (10 if m15["dir"] >= 0 else 0)
            summary = ("Springs on the higher timeframes hint at accumulation; a sign of strength is still needed. "
                       if springs else "The higher timeframes are in markup. ") + (
                "The 15m shows an upthrust, so expect a pullback before continuation." if m15["dir"] < 0
                else "The 15m shows no distribution signs.")
        else:
            bias, label, conf = "WAIT", "RANGE", 30
            summary = "Daily and 4H do not agree on a phase. Wait for a spring or upthrust at the range edges."
        rows = [["Daily stage", d["text"]], ["4H stage", h4["text"]], ["15m stage", m15["text"]]]
        if target:
            rows.append(["HTF target", f"{ctx.sp(target):,.0f} (untouched liquidity)"])
        if flip:
            word = "re-accumulation possible" if htf < 0 else "distribution risk"
            rows.append(["Flip level", f"4H close {'above' if htf < 0 else 'below'} {ctx.sp(flip):,.0f} = {word}"])
        metrics = {"htf_dir": htf, "ltf_dir": m15["dir"]}
        if m15["lps"]:
            metrics.update(lps_lo=ctx.sp(m15["lps"][0]), lps_hi=ctx.sp(m15["lps"][1]))
        return self.result(ctx, bias=bias, bias_label=label, confidence=min(conf, 80), subtitle="Daily + 4H + 15m",
                           headline=summary.split(". ")[0], summary=summary, rows=rows, metrics=metrics,
                           timeframe="1d/4h/15m",
                           levels=[self.level(ctx, sets["4h"], "support" if htf > 0 else "resistance", flip, "Wyckoff flip level"),
                                   self.level(ctx, sets["1d"], "target", target, "Wyckoff HTF target")])
