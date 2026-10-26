"""Session and macro: trading session, weekend risk, US dollar (DXY), silver and stocks."""
from datetime import timezone
from zoneinfo import ZoneInfo

from core.indicators import ema
from .base import BaseAgent

NY = ZoneInfo("America/New_York")


def session(now_utc):
    ny = now_utc.astimezone(NY)
    h, wd = now_utc.hour, ny.weekday()
    if wd == 5 or (wd == 4 and ny.hour >= 17) or (wd == 6 and ny.hour < 18):
        return "Market closed (weekend)"
    if ny.hour == 17:
        return "Daily break (17:00-18:00 New York)"
    if 12 <= h < 16:
        return "London + New York overlap (most liquid)"
    if 7 <= h < 12:
        return "London session"
    if 16 <= h < 21:
        return "New York afternoon (liquidity fading)"
    return "Asian session (quieter, ranges common)"


def trend_of(candles, n_fast=20, n_slow=50):
    closes = [c.c for c in candles]
    if len(closes) < n_slow + 5:
        return None, None
    f, s = ema(closes, n_fast)[-1], ema(closes, n_slow)[-1]
    chg = (closes[-1] - closes[-25]) / closes[-25] * 100
    return (1 if f > s and chg > 0 else -1 if f < s and chg < 0 else 0), chg


class SessionMacroAgent(BaseAgent):
    name, label, weight = "macro", "Session and macro", 1.0

    async def analyze(self, ctx):
        now = ctx.generated_at.astimezone(timezone.utc)
        ny = now.astimezone(NY)
        rows, score, warnings = [], 0.0, ["No economic calendar is connected: check CPI, Fed and jobs-report times yourself."]
        sess = session(now)
        day = ny.strftime("%A")
        rows.append(["Session", f"{day} · {sess}"])
        weekend = (ny.weekday() == 4 and ny.hour >= 10) or "weekend" in sess
        if weekend:
            rows.append(["Weekend risk", "Gaps can happen over the weekend. No new positions to hold into it."])
        elif ny.weekday() == 0 and ny.hour < 6:
            rows.append(["Monday open", "Watch for a gap from Friday's close."])

        dxy_dir, dxy_chg = trend_of(ctx.markets.get("dxy_1h", []))
        if dxy_dir is not None:
            word = {1: "rising: headwind for gold", -1: "falling: tailwind for gold", 0: "flat: no strong push"}[dxy_dir]
            rows.append(["US dollar (DXY)", f"{dxy_chg:+.2f}% over ~25h, {word}"])
            score -= dxy_dir
        else:
            warnings.append("Dollar index data unavailable.")
        ag_dir, ag_chg = trend_of(ctx.markets.get("silver_1h", []))
        h1 = ctx.struct("1h")
        g_dir, g_chg = trend_of(h1.candles) if h1 else (None, None)
        if ag_dir is not None and g_dir is not None:
            agree = ag_dir == g_dir and g_dir != 0
            rows.append(["Silver", f"{ag_chg:+.2f}% over ~25h ({'confirms' if agree else 'does not confirm'} gold's move)"])
            if agree:
                score += 0.5 * g_dir
        spx = ctx.markets.get("sp500_1d", [])
        if len(spx) > 6:
            chg = (spx[-1].c - spx[-6].c) / spx[-6].c * 100
            mood = "risk-off (can support gold)" if chg < -2 else "risk-on" if chg > 2 else "calm"
            rows.append(["Stocks (S&P 500)", f"{chg:+.1f}% over 5 days, {mood}"])
            if chg < -2:
                score += 0.5
        d = ctx.struct("1d")
        if d and len(d.candles) > 2:
            y = d.candles[-2]
            kind = "bear close" if y.c < y.o else "bull close"
            wick = " (long upper wick)" if (y.h - max(y.o, y.c)) > abs(y.c - y.o) else \
                   " (long lower wick)" if (min(y.o, y.c) - y.l) > abs(y.c - y.o) else ""
            rows.append(["Last daily close", f"H {ctx.sp(y.h):,.0f} · C {ctx.sp(y.c):,.0f} · {kind}{wick}"])
            score += -0.5 if y.c < y.o else 0.5

        if score <= -1:
            bias, label = "SELL", "SELL lean"
            summary = "Macro leans against gold (stronger dollar)."
        elif score >= 1:
            bias, label = "BUY", "BUY lean"
            summary = "Macro leans in gold's favour (weaker dollar or risk-off)."
        else:
            bias, label, summary = "WAIT", "NEUTRAL", "Macro gives no strong push either way."
        if weekend:
            summary += " Do not hold new trades over the weekend without 4H confirmation."
        return self.result(ctx, bias=bias, bias_label=label, confidence=min(70, int(30 + 15 * abs(score))),
                           subtitle=f"{day} · {'weekend risk' if weekend else sess.split(' (')[0]}",
                           headline=summary.split(".")[0], summary=summary, rows=rows, warnings=warnings,
                           timeframe="macro", metrics={"weekend": "yes" if weekend else "no", "score": score})
