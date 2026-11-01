"""ICT agent: the time-and-sequence model on 15m candles.

  1. Liquidity: previous day high / low (PDH / PDL), today's Asian range high / low (20:00-00:00 New York) and the
     latest 15m swing high / low. Buy-side liquidity (BSL) rests above highs, sell-side (SSL) below lows.
  2. Sweep: a candle trades through a pool and closes back inside (BSL taken -> look for shorts, SSL taken -> longs).
  3. CHoCH / market structure shift: after the sweep, a candle closes beyond the swing that started the sweep leg,
     with displacement (a body at least 1.5x the median body of the last 20 candles).
  4. FVG: the displacement leaves a fair-value gap; the entry is a return into it, the stop goes beyond the sweep
     extreme, the target is the opposite pool.
  5. Premium / discount: the dealing range is the sweep leg (sweep extreme to the displacement's far end). Sells
     only from premium (entry above 50% of the range), buys only from discount; the 62-79% OTE scores higher.
  6. Timing: London (02:00-05:00 New York) and New York (07:00-11:00) killzones score higher; the 1H trend agreeing
     scores higher; a sweep of PDH/PDL or the Asian range counts more than a plain swing.

Votes only when the whole sequence happened in the last 3 hours and price has not gone back beyond the sweep
extreme or already reached the target. Otherwise it reports the pools and what it is waiting for, and does not vote.
Works on 15m/1H/Daily only, so live and backtest results mean the same thing.
"""
from datetime import datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from core.structure import highs, lows, tf_bias, zigzag
from .base import BaseAgent

NY = ZoneInfo("America/New_York")
RECENT_BARS = 12              # the setup must be fresh: sweep within the last 3 hours of 15m candles
DISPLACEMENT = 1.5            # MSS candle body vs the median body of the last 20 candles
KILLZONES = ((2, 5, "London killzone"), (7, 11, "New York killzone"))
PD_FILTER = True              # sell only from premium, buy only from discount of the sweep leg (the dealing range)
OTE = (0.62, 0.79)            # optimal trade entry: 62-79% retracement of the dealing range


def ny(t):
    return datetime.fromtimestamp(t, NY)


def killzone(t) -> str | None:
    h = ny(t).hour
    return next((name for a, b, name in KILLZONES if a <= h < b), None)


def asian_range(m15):
    """High/low of the latest 20:00-00:00 New York session that has finished."""
    day0 = ny(m15[-1].t).replace(hour=0, minute=0, second=0, microsecond=0)     # it ends at midnight New York
    a, b = (day0 - timedelta(hours=4)).timestamp(), day0.timestamp()
    bars = [c for c in m15 if a <= c.t < b]
    if len(bars) < 8:
        return None
    return max(c.h for c in bars), min(c.l for c in bars)


class ICTAgent(BaseAgent):
    name, label, weight = "ict", "ICT", 1.0
    pd_filter = PD_FILTER

    async def analyze(self, ctx):
        m15, h1, d = ctx.struct("15m"), ctx.struct("1h"), ctx.struct("1d")
        if any(cs is None or len(cs.candles) < 60 for cs in (m15, h1)) or d is None or len(d.candles) < 2:
            return self.insufficient(ctx, "Needs 15m and 1H candles (60+) and at least 2 daily candles.")
        cl = m15.candles
        price = cl[-1].c
        prev_day = d.candles[-2]                       # the last finished day (the newest one is still forming)
        pools = [("PDH", prev_day.h, "BSL"), ("PDL", prev_day.l, "SSL")]
        ar = asian_range(cl)
        if ar:
            pools += [("Asian high", ar[0], "BSL"), ("Asian low", ar[1], "SSL")]
        piv = zigzag(cl[:-RECENT_BARS] or cl, 2)
        sh, sl = highs(piv), lows(piv)
        if sh:
            pools.append(("15m swing high", sh[-1].price, "BSL"))
        if sl:
            pools.append(("15m swing low", sl[-1].price, "SSL"))

        bodies = [abs(c.c - c.o) for c in cl[-21:-1]]
        big = DISPLACEMENT * (median(bodies) or 0.01)
        n = len(cl)
        found = []
        for j in range(n - 1, n - 1 - RECENT_BARS, -1):          # newest sweep first
            c = cl[j]
            for pname, lvl, kind in pools:
                if kind == "BSL" and c.h > lvl and c.c < lvl:
                    side, ext = "SELL", max(x.h for x in cl[j:])
                elif kind == "SSL" and c.l < lvl and c.c > lvl:
                    side, ext = "BUY", min(x.l for x in cl[j:])
                else:
                    continue
                leg = cl[max(0, j - 8):j + 1]
                swing = min(x.l for x in leg) if side == "SELL" else max(x.h for x in leg)
                mss = next((k for k in range(j + 1, n) if (cl[k].c < swing if side == "SELL" else cl[k].c > swing)
                            and abs(cl[k].c - cl[k].o) >= big), None)
                fvg = None
                if mss is not None:
                    for k in range(j + 2, n):
                        a, b = cl[k - 2], cl[k]
                        if side == "SELL" and b.h < a.l:
                            fvg = (b.h, a.l)
                        if side == "BUY" and b.l > a.h:
                            fvg = (a.h, b.l)
                opp = [p for p in pools if p[2] == ("SSL" if side == "SELL" else "BSL")
                       and ((p[1] < price) if side == "SELL" else (p[1] > price))]
                target = (max(opp, key=lambda p: p[1]) if side == "SELL" else min(opp, key=lambda p: p[1])) if opp else None
                found.append(dict(side=side, pool=pname, lvl=lvl, ext=ext, j=j, mss=mss, fvg=fvg, target=target, kz=killzone(c.t)))
        # the newest complete sequence (sweep + CHoCH) wins; otherwise the newest sweep, to say what it waits for
        setup = next((f for f in found if f["mss"] is not None), found[0] if found else None)

        hb = tf_bias(h1.candles, 2.5)["bias"]
        rows = [["Buy-side liquidity", " · ".join(f"{p[0]} {ctx.sp(p[1]):,.0f}" for p in pools if p[2] == "BSL" and p[1] > price) or "none above"],
                ["Sell-side liquidity", " · ".join(f"{p[0]} {ctx.sp(p[1]):,.0f}" for p in pools if p[2] == "SSL" and p[1] < price) or "none below"],
                ["Session", killzone(cl[-1].t) or "outside the killzones"]]
        levels, metrics = [], {}
        bias, conf, label = "WAIT", 25, "NO SETUP"
        summary = "No liquidity sweep in the last 3 hours. Waiting for price to take a pool (PDH/PDL, Asian range or a swing)."
        if setup:
            s = setup
            took = f"{s['pool']} {ctx.sp(s['lvl']):,.0f} {'BSL' if s['side'] == 'SELL' else 'SSL'} swept"
            rows.append(["Sweep", took + (f" in the {s['kz']}" if s["kz"] else "")])
            invalid = price > s["ext"] if s["side"] == "SELL" else price < s["ext"]
            reached = s["target"] and ((price <= s["target"][1]) if s["side"] == "SELL" else (price >= s["target"][1]))
            if s["mss"] is None:
                label = "SWEPT · NO CHoCH"
                summary = f"{took}. Waiting for a CHoCH: a strong 15m close {'below' if s['side'] == 'SELL' else 'above'} the swing that started the sweep."
            elif invalid:
                label = "FAILED"
                summary = f"{took}, but price went back beyond the sweep extreme {ctx.sp(s['ext']):,.0f}: setup failed."
            elif reached:
                label = "DONE"
                summary = f"{took} and the move already reached {s['target'][0]}. No new entry."
            else:
                leg = cl[s["j"]:]                      # dealing range: the sweep leg
                hi, lo = (s["ext"], min(x.l for x in leg)) if s["side"] == "SELL" else (max(x.h for x in leg), s["ext"])
                entry = (s["fvg"][0] + s["fvg"][1]) / 2 if s["fvg"] else price
                pos = (entry - lo) / (hi - lo) if hi > lo else 0.5          # 0 = range low, 1 = range high
                depth = pos if s["side"] == "SELL" else 1 - pos            # how deep into premium / discount
                zone_ok, in_ote = depth > 0.5, OTE[0] <= depth <= OTE[1]
                zone = ("premium" if pos > 0.5 else "discount") + (" (OTE)" if in_ote else "")
                rows.append(["Dealing range", f"{ctx.sp(lo):,.0f}-{ctx.sp(hi):,.0f} · equilibrium {ctx.sp((hi + lo) / 2):,.0f} · entry in {zone}"])
                metrics.update(eq=ctx.sp((hi + lo) / 2), zone=zone, depth=round(depth, 2))
            if setup and s["mss"] is not None and not invalid and not reached and self.pd_filter and not zone_ok:
                label = f"{s['side']} SKIPPED"
                rule, way = ("sells only from premium", "above") if s["side"] == "SELL" else ("buys only from discount", "below")
                summary = (f"{took}, then a CHoCH, but the entry is in {zone}: ICT {rule}. "
                           f"Wait for price to return {way} equilibrium {ctx.sp((hi + lo) / 2):,.0f}.")
            elif setup and s["mss"] is not None and not invalid and not reached:
                rows.append(["CHoCH / MSS", f"15m displacement {'down' if s['side'] == 'SELL' else 'up'} confirmed"])
                if s["fvg"]:
                    rows.append(["Entry FVG", f"{ctx.sp(s['fvg'][0]):,.0f}-{ctx.sp(s['fvg'][1]):,.0f}"])
                    levels.append(self.level(ctx, m15, "entry", (s["fvg"][0] + s["fvg"][1]) / 2, "ICT entry: return into the FVG"))
                levels.append(self.level(ctx, m15, "stop", s["ext"], "ICT invalidation: beyond the sweep extreme"))
                if s["target"]:
                    levels.append(self.level(ctx, m15, "target", s["target"][1], f"ICT target: {s['target'][0]}"))
                    rows.append(["Target", f"{s['target'][0]} {ctx.sp(s['target'][1]):,.0f}"])
                with_htf = s["side"] in hb
                strong_pool = s["pool"] in ("PDH", "PDL", "Asian high", "Asian low")
                conf = 50 + (10 if s["kz"] else -5) + (10 if with_htf else -10) + (5 if strong_pool else 0) + (5 if s["fvg"] else 0) + (5 if in_ote else 0)
                bias, label = s["side"], f"{s['side']} (sweep + CHoCH)"
                summary = (f"{took}, then a CHoCH with displacement. "
                           + (f"Entry on a return into the FVG, stop beyond {ctx.sp(s['ext']):,.0f}. " if s["fvg"] else f"Stop beyond {ctx.sp(s['ext']):,.0f}. ")
                           + f"Entry in {zone}. "
                           + ("With the 1H trend." if with_htf else "Against the 1H trend: smaller confidence."))
                metrics.update(sweep_level=ctx.sp(s["lvl"]), sweep_extreme=ctx.sp(s["ext"]), in_killzone=bool(s["kz"]), with_htf=with_htf)
        return self.result(ctx, bias=bias, bias_label=label, confidence=max(0, min(conf, 80)), subtitle="Sweep · CHoCH · FVG",
                           headline=summary.split(". ")[0], summary=summary, rows=rows, metrics=metrics,
                           levels=levels, timeframe="15m/1h/1d")
