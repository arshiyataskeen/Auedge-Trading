"""Data-quality and risk checks. Never votes BUY/SELL; can veto the Chief."""
from datetime import timezone
from zoneinfo import ZoneInfo

from core.indicators import atr, clamp
from .base import BaseAgent

NY = ZoneInfo("America/New_York")


def market_closed(now_utc) -> str | None:
    """Gold trades Sun 18:00 to Fri 17:00 New York time, with a daily 17:00-18:00 break."""
    ny = now_utc.astimezone(NY)
    wd, h = ny.weekday(), ny.hour          # Mon=0 .. Sun=6
    if wd == 5 or (wd == 4 and h >= 17) or (wd == 6 and h < 18):
        return "Weekend: the gold market is closed."
    if h == 17:
        return "Daily trading break (17:00-18:00 New York time)."
    return None


class RiskGuardAgent(BaseAgent):
    name, label, weight, votes = "risk", "Risk guard (data quality)", 0, False

    async def analyze(self, ctx):
        warnings, reasons, veto, score = [], [], False, 100
        s = ctx.spot
        if s is None:
            veto, score = True, 0
            reasons.append("No live spot price could be loaded.")
        else:
            reasons.append(f"Spot {s.price:.2f} from {s.price_source}, updated {s.age_seconds:.0f}s ago "
                           f"(our own check; the API says '{s.api_data_state.get('status', '?')}').")
            if s.stale:
                veto, score = True, score - 60
                warnings.append(f"Price is STALE ({s.age_seconds / 60:.0f} min old). No suggestion should be acted on.")
        closed = market_closed(ctx.generated_at.astimezone(timezone.utc))
        if closed:
            veto, score = True, score - 30
            warnings.append(closed)
        cs = ctx.candles.get("spot_15m")
        if cs and len(cs.closed()) > 70:
            a = [x for x in atr(cs.closed()) if x is not None]
            base = sum(a[-50:]) / 50 if len(a) >= 50 else 0
            ratio = a[-1] / base if base > 0 else 1.0           # flat candles (e.g. weekend samples): no spike
            reasons.append(f"15m volatility is {ratio:.2f}x normal.")
            if ratio > 3:
                veto, score = True, score - 30
                warnings.append("Extreme volatility spike (news?). Standing aside is safer.")
            elif ratio > 2:
                score -= 15
                warnings.append("Volatility is unusually high: wider stops and smaller size are needed.")
        if ctx.futures_gap is None and s is not None:
            veto, score = True, score - 40
            warnings.append("The futures-spot gap could not be measured, so levels can't be converted to spot prices. "
                            "No trade until the next analysis.")
        if ctx.futures_gap is not None:
            reasons.append(f"Futures minus spot: {ctx.futures_gap:+.2f} (futures are delayed about "
                           f"{(ctx.futures_last_age_s or 0) / 60:.0f} min).")
            if ctx.futures_gap < -15 or ctx.futures_gap > 80:
                score -= 15
                warnings.append("Spot and futures disagree more than usual; one source may be off.")
        if ctx.intraday_coverage_s is not None and ctx.intraday_coverage_s < 40 * 3600:
            score -= 10
            warnings.append(f"Only {ctx.intraday_coverage_s / 3600:.0f}h of spot samples (48h expected).")
        if ctx.intraday_interval_s and ctx.intraday_interval_s > 120:
            warnings.append(f"Spot is sampled every {ctx.intraday_interval_s // 60} min, so spot candles "
                            f"below {3 * ctx.intraday_interval_s // 60} min cannot be built; futures are used there.")
        for e in ctx.errors:
            score -= 10
            warnings.append(f"Data problem: {e}")
        warnings.append("All prices are indicative mid-market rates, not broker quotes; your broker differs by the spread.")
        head = "STOP: do not act on suggestions now" if veto else "Data OK" if score >= 80 else "Data usable, with caveats"
        return self.result(ctx, bias="WAIT", confidence=clamp(score), headline=head, reasons=reasons,
                           warnings=warnings, veto=veto, metrics={"data_quality": clamp(score)})
