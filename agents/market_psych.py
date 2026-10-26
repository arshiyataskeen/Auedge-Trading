"""Market psychology: how the crowd of traders is behaving, read as a contrarian signal at extremes.

Five readings, each scored on a greed (+) / fear (-) axis:
1. Big-money positioning (CFTC COT, weekly): speculators' net long vs the last 3 years. Near the top = crowded long.
2. Stretch: 4H RSI and distance from the 4H 50-EMA in ATRs. Far above = euphoria, far below = panic.
3. Climax volume: a huge-volume, wide 1H candle at the end of a run = buying frenzy or panic selling (often exhaustion).
4. Trapped traders: a breakout that failed and snapped back (or a wick through a level that closed back) leaves
   breakout traders stuck. Shown as a warning and used to confirm an extreme; alone it tested as a coin flip.
5. Fear level: 15m volatility vs normal; a spike in a falling market is fear, in a rising market is greed.
Mood = Panic / Fear / Neutral / Greed / Euphoria. Bias: only against an extreme crowd, or with trapped traders.
"""
from statistics import median

from core import cot
from core.indicators import atr, ema, rsi
from core.structure import sweep
from .base import BaseAgent

MOODS = [(-4, "PANIC"), (-1.5, "FEAR"), (1.5, "NEUTRAL"), (4, "GREED"), (99, "EUPHORIA")]


def mood_of(score: float) -> str:
    return next(name for edge, name in MOODS if score < edge) if score < 4 else "EUPHORIA"


def trapped(cl, look: int = 12, ref: int = 20):
    """Failed breakout in the last `look` candles: (side_trapped, level, bars_ago) or None.
    'longs' = price closed above the prior high, then closed back below it (breakout buyers stuck)."""
    n = len(cl)
    if n < ref + look + 2:
        return None
    for j in range(n - 2, n - look - 1, -1):
        prior = cl[j - ref:j]
        hi, lo = max(c.h for c in prior), min(c.l for c in prior)
        if cl[j].c > hi and cl[-1].c < hi and any(c.c < hi for c in cl[j + 1:]):
            return "longs", hi, n - 1 - j
        if cl[j].c < lo and cl[-1].c > lo and any(c.c > lo for c in cl[j + 1:]):
            return "shorts", lo, n - 1 - j
    sw = sweep(cl, ref, look)                 # wick through and closed back in the same candle
    if sw:
        return ("longs" if sw[0] == "upthrust" else "shorts"), sw[1], n - 1 - sw[2]
    return None


class MarketPsychAgent(BaseAgent):
    name, label, weight = "sentiment", "Market psychology", 1.0

    async def analyze(self, ctx):
        h4, h1, m15 = ctx.struct("4h"), ctx.struct("1h"), ctx.struct("15m")
        if any(cs is None or len(cs.candles) < 60 for cs in (h4, h1, m15)):
            return self.insufficient(ctx, "Needs 4H, 1H and 15m candles (60+ each).")
        rows, warnings, levels, parts = [], [], [], {}
        greed = 0.0

        # 1) COT positioning (weekly)
        c = cot.view(ctx.cot, ctx.generated_at.timestamp()) if ctx.cot else None
        if c:
            s = 2 if c["index"] >= 90 else 1 if c["index"] >= 75 else -2 if c["index"] <= 10 else -1 if c["index"] <= 25 else 0
            greed += s
            parts["cot"] = s
            crowd = ("crowded LONG" if s > 0 else "crowded SHORT" if s < 0 else "not extreme")
            rows.append(["Big money (COT)", f"speculators {c['long_pct']}% long · {c['index']}/100 vs 3 years · {crowd}"])
            rows.append(["COT this week", f"net {c['net']:+,} contracts ({c['change']:+,}) · report {c['date']}"])
        else:
            warnings.append("COT positioning unavailable (weekly CFTC data could not be loaded).")

        # 2) Stretch (4H RSI + distance from the 4H 50-EMA in ATRs)
        cl4 = h4.candles
        r4 = rsi([x.c for x in cl4])[-1]
        e50 = ema([x.c for x in cl4], 50)[-1]
        a4 = atr(cl4)[-1] or 1
        stretch = (cl4[-1].c - e50) / a4 if e50 else 0
        s = 0
        if r4 is not None:
            if r4 >= 75 or stretch >= 4: s = 2
            elif r4 >= 65 or stretch >= 2.5: s = 1
            elif r4 <= 25 or stretch <= -4: s = -2
            elif r4 <= 35 or stretch <= -2.5: s = -1
            rows.append(["Stretch (4H)", f"RSI {r4:.0f} · {stretch:+.1f} ATR from the 50-EMA"])
        greed += s
        parts["stretch"] = s

        # 3) Climax volume on 1H (only if the feed has volume)
        cl1 = h1.candles
        vols = [x.v for x in cl1[-60:-1] if x.v]
        a1 = atr(cl1)[-1] or 1
        s, climax = 0, None
        if len(vols) >= 30:
            med = median(vols)
            for x in cl1[-6:]:
                if x.v > 2.5 * med and (x.h - x.l) > 1.8 * a1:
                    run = x.c - cl1[-13].c
                    if abs(run) > 2 * a1:
                        climax = ("buying frenzy" if x.c > x.o else "panic selling", x)
            if climax:
                s = 1.5 if climax[0] == "buying frenzy" else -1.5
                rows.append(["Climax volume", f"{climax[0]}: {climax[1].v / med:.1f}x normal volume on a wide 1H candle"])
            else:
                rows.append(["Climax volume", "none in the last 6 hours"])
        greed += s
        parts["climax"] = s

        # 4) Trapped traders (15m first, then 1H)
        tr = trapped(m15.candles) or trapped(cl1, 6, 20)
        if tr:
            who, lvl, ago = tr
            rows.append(["Trapped traders", f"breakout {who} trapped at {ctx.sp(lvl):,.0f} ({ago} candles ago): "
                                            f"their exits push price {'down' if who == 'longs' else 'up'}"])
            levels.append(self.level(ctx, m15, "pivot", lvl, f"Failed breakout: {who} trapped"))
        else:
            rows.append(["Trapped traders", "none right now"])

        # 5) Fear level (15m volatility vs normal)
        a15 = [x for x in atr(m15.candles) if x]
        s = 0
        if len(a15) > 50:
            ratio = a15[-1] / (sum(a15[-50:]) / 50)
            move = m15.candles[-1].c - m15.candles[-9].c
            if ratio > 1.8:
                s = 1 if move > 0 else -1
            rows.append(["Fear level", f"volatility {ratio:.1f}x normal · "
                                       f"{'nervous' if ratio > 1.8 else 'calm' if ratio < 0.7 else 'normal'}"])
        greed += s
        parts["fear"] = s

        mood = mood_of(greed)
        rows.insert(0, ["Crowd mood", f"{mood} (score {greed:+.1f}, from -6 panic to +7 euphoria)"])

        # Bias: fade an extreme crowd only with a sign of exhaustion. Trapped traders alone were a coin flip in the
        # 6-month study (50% over 1,258 calls), so they are a warning and a confirmation, never a vote on their own.
        bias, conf, label = "WAIT", 30, mood
        if tr:
            warnings.append(f"Breakout {tr[0]} trapped near {ctx.sp(tr[1]):,.0f}: watch for a move "
                            f"{'down' if tr[0] == 'longs' else 'up'} (a warning, not a signal on its own).")
        if greed >= 3 and (tr and tr[0] == "longs" or climax and climax[0] == "buying frenzy"):
            bias, conf = "SELL", 65
        elif greed <= -3 and (tr and tr[0] == "shorts" or climax and climax[0] == "panic selling"):
            bias, conf = "BUY", 65
        if bias != "WAIT":
            label = f"{mood} · {bias}"
        summary = {
            "EUPHORIA": "The crowd is euphoric: everyone is already long. Late buyers become fuel for a drop.",
            "GREED": "The crowd is greedy and stretched. Avoid chasing longs; wait for pullbacks.",
            "NEUTRAL": "No crowd extreme. Positioning and stretch are normal.",
            "FEAR": "The crowd is fearful. Avoid panic-selling lows; watch for buyers to step in.",
            "PANIC": "The crowd is panicking. Selling is exhausted more often than not; wait for a turn to buy.",
        }[mood]
        if tr:
            summary += f" Warning: breakout {tr[0]} are trapped near {ctx.sp(tr[1]):,.0f}."
        return self.result(ctx, bias=bias, bias_label=label, confidence=conf, headline=summary.split(".")[0],
                           summary=summary, rows=rows, warnings=warnings, levels=levels,
                           subtitle="COT · stretch · volume · trapped · fear", timeframe="crowd",
                           metrics={"mood": mood, "greed": round(greed, 1), **parts,
                                    "cot_index": c["index"] if c else "n/a"})
