"""Discipline coach: protects the trader from the usual behavioural mistakes. Never votes BUY/SELL.

Hard rules (block any new trade until they clear):
- At most 2 trades per trading day (18:00-17:00 New York).
- Stop for the day after 2 losses (revenge trading starts here).
- 60-minute cool-down after any loss.
- No new trade while one is still open (manage it, don't add).
- No new trades on Friday after 12:00 New York (weekend gap risk).
- No new trades 30 min before/after CPI and the jobs report, 30 min before to 60 min after a Fed decision.
Soft rules (warnings; chasing also turns a "NOW" entry into "wait for a pullback"):
- Chasing: price already ran more than 1.5x the 1H ATR in the last hour.
- Losing streak of 3+: cut risk to 0.5% until a win.
- Already +2R today: overconfidence risk, protect the day.
The trade counts come from the Chief's own track record (data/track.db). Your real trades can be entered on the
dashboard ("My day"); those are applied in the browser.
"""
from datetime import timezone
from zoneinfo import ZoneInfo

from core import news, track
from core.indicators import atr
from .base import BaseAgent

NY = ZoneInfo("America/New_York")
MAX_TRADES_PER_DAY = 2
MAX_LOSSES_PER_DAY = 2
COOLDOWN_AFTER_LOSS_S = 60 * 60
CHASE_ATR = 1.5
STREAK_WARN = 3
BIG_DAY_R = 2.0
FRIDAY_CUTOFF_NY = 12
LOT = 0.1                       # fixed lot: 0.1 = $10 per $1 move
DAY_MAX_LOSS = 350.0            # dollars per trading day: stop for the day at this loss
DAY_MAX_PROFIT = 150.0          # dollars per trading day: stop for the day at this profit


def _gates_on() -> bool:
    from core.newsintel.mode import mode
    return mode() != "off"


def assess(stats: dict, now_utc, m15: list, h1: list, m5: list | None = None, spread: float | None = None,
           intel: dict | None = None, art=None, spread_median: float | None = None) -> dict:
    """Pure rule check (no I/O), so the backtest can reuse it. Returns blocks, warnings, chase flag and a score."""
    blocks, warns, rows = [], [], []
    now_s = now_utc.timestamp()
    rows.append(["Chief trades today", f"{stats['trades_today']} of {MAX_TRADES_PER_DAY} allowed"])
    usd = stats.get("usd_today", 0.0)
    rows.append(["Today's result", f"{stats['wins_today']} won · {stats['losses_today']} lost · "
                                   f"{'+' if usd >= 0 else '-'}${abs(usd):,.0f} at {LOT} lot"])
    rows.append(["Daily limits", f"stop at -${DAY_MAX_LOSS:,.0f} or +${DAY_MAX_PROFIT:,.0f}"])
    if usd <= -DAY_MAX_LOSS:
        blocks.append(f"Daily loss limit reached (-${abs(usd):,.0f}). Stop for today; protect the account.")
    if usd >= DAY_MAX_PROFIT:
        blocks.append(f"Daily profit target reached (+${usd:,.0f}). Done for today: keep the profit.")
    if stats["trades_today"] >= MAX_TRADES_PER_DAY:
        blocks.append(f"Daily limit reached ({MAX_TRADES_PER_DAY} trades). Done for today: more trades usually means worse trades.")
    if stats["losses_today"] >= MAX_LOSSES_PER_DAY:
        blocks.append(f"{stats['losses_today']} losses today. Stop for the day; trying to win it back is how small losses become big ones.")
    if stats["last_loss_ts"] and now_s - stats["last_loss_ts"] < COOLDOWN_AFTER_LOSS_S:
        mins = int((COOLDOWN_AFTER_LOSS_S - (now_s - stats["last_loss_ts"])) / 60) + 1
        blocks.append(f"Cool-down after a loss: wait {mins} more min before the next trade.")
        rows.append(["Cool-down", f"{mins} min left"])
    if stats["open"]:
        blocks.append("A trade is still open. Manage that one (stop and target are set); don't add another.")
    ny = now_utc.astimezone(NY)
    if ny.weekday() == 4 and ny.hour >= FRIDAY_CUTOFF_NY:
        blocks.append("Friday afternoon: no new trades to hold into the weekend gap.")
    ev = news.blackout(now_s)
    if ev:
        blocks.append(f"News: {news.label(ev, now_s)}. No new trades around it; spreads widen and price whips both ways.")
    if (m5 is not None or spread is not None or intel is not None) and _gates_on():
        from core.newsintel import gates
        if art is None:
            from agents.news_intel import artifacts
            art = artifacts()
        g = gates.avoid(now_s, m5, spread, spread_median, intel, art)
        if g and not (g[0] == "calendar" and ev):
            blocks.append(f"News gate ({g[0]}): {g[1]}")
    nxt = [e for e in news.upcoming(now_s, 24 * 7) if e["t"] > now_s]
    if nxt:
        rows.append(["Next big news", news.label(nxt[0], now_s)])
        if not ev and nxt[0]["t"] - now_s < 2 * 3600:
            warns.append(f"{news.label(nxt[0], now_s)}: a trade opened now may still be running into it.")

    chase = False
    if len(m15) >= 5 and len(h1) >= 20:
        a1 = atr(h1)[-1] or 0
        move = m15[-1].c - m15[-5].c
        if a1 and abs(move) > CHASE_ATR * a1:
            chase = True
            warns.append(f"Price moved {abs(move):.0f} in the last hour ({abs(move) / a1:.1f}x normal). "
                         f"Don't chase it: wait for a pullback.")
        rows.append(["Last hour move", f"{move:+.1f} ({abs(move) / a1:.1f}x the 1H ATR)" if a1 else f"{move:+.1f}"])
    if stats["losing_streak"] >= STREAK_WARN:
        warns.append(f"{stats['losing_streak']} losses in a row. Normal in trading, but cut risk to 0.5% until the next win.")
    if stats["r_today"] >= BIG_DAY_R:
        warns.append(f"Already {stats['r_today']:+.1f}R today. Good day: protect it, overconfidence is the next risk.")
    rows.append(["Losing streak", str(stats["losing_streak"])])
    rows.append(["Suggested risk", "0.5% of account" if stats["losing_streak"] >= STREAK_WARN else "1% of account"])
    score = max(0, 100 - 40 * len(blocks) - 15 * len(warns))
    return {"blocks": blocks, "warns": warns, "chase": chase, "rows": rows, "score": score}


class PsychologyAgent(BaseAgent):
    name, label, weight, votes = "psychology", "Discipline coach", 0, False

    async def analyze(self, ctx):
        stats = track.discipline_stats(ctx.generated_at.timestamp(), LOT)
        m15, h1 = ctx.struct("15m"), ctx.struct("1h")
        m5 = None
        try:
            from core.newsintel import live
            m5 = live._done(live._m5_set(ctx), 300, int(ctx.generated_at.timestamp())) or None
        except Exception:  # noqa: BLE001 - the gate is optional; the other rules still run
            m5 = None
        from core.newsintel.mode import NEWS_AGENT
        intel = next((r.extra for r in (ctx.prior or []) if r.agent == NEWS_AGENT), None) or None
        a = assess(stats, ctx.generated_at.astimezone(timezone.utc), m15.candles if m15 else [], h1.candles if h1 else [],
                   m5=m5, intel=intel)
        if a["blocks"]:
            label, head = "STOP", a["blocks"][0]
        elif a["warns"]:
            label, head = "CAUTION", a["warns"][0]
        else:
            label, head = "CLEAR", "Mindset check passed: trade only the plan, with the stop set before you enter."
        summary = " ".join(a["blocks"] + a["warns"]) or head
        return self.result(ctx, bias="WAIT", bias_label=label, confidence=a["score"], veto=bool(a["blocks"]),
                           headline=head, summary=summary, rows=a["rows"], warnings=a["blocks"] + a["warns"],
                           subtitle="Discipline · not a vote", timeframe="discipline",
                           metrics={"chase": "yes" if a["chase"] else "no", "score": a["score"],
                                    "usd_today": stats.get("usd_today", 0.0)})


def apply_to_plan(report, psych) -> None:
    """Hard rules cancel any new trade; chasing turns a 'NOW' entry into 'wait for a pullback'."""
    from .chief import TradePlan
    plan = report.plan
    if plan.kind == "none":
        return
    if psych.status != "OK":
        if plan.kind == "now":
            report.plan = TradePlan(kind="none", action="NO TRADE (discipline check unavailable)", side=plan.side, steps=[
                "The Discipline coach could not check today's limits, so no new trade this time.",
                f"The analysis said: {plan.action}. The next analysis (every 15 minutes) tries again."])
            report.headline = "Discipline check unavailable: no new trade"
            report.bias = "WAIT"
        return
    if plan.kind == "now" and plan.stop is not None and not psych.veto:
        risk_usd = abs((plan.entry_lo + plan.entry_hi) / 2 - plan.stop) * 100 * LOT
        if float(psych.metrics.get("usd_today", 0)) - risk_usd < -DAY_MAX_LOSS:
            report.plan = TradePlan(kind="none", action="NO TRADE (daily loss limit)", side=plan.side, steps=[
                f"This trade risks ${risk_usd:,.0f} at {LOT} lot; if its stop is hit, today would end beyond the "
                f"-${DAY_MAX_LOSS:,.0f} daily limit. Skip it.", f"The analysis said: {plan.action}."])
            report.headline = "Discipline: the stop is too wide for today's loss limit"
            report.bias = "WAIT"
            return
    if psych.veto:
        reason = psych.warnings[0]
        report.plan = TradePlan(kind="none", action="NO TRADE (discipline)",
                                steps=[reason, f"The analysis said: {plan.action}. Skip it; the next setup will come."])
        report.headline = "Discipline: " + reason
        report.bias = "WAIT"
    elif psych.metrics.get("chase") == "yes" and plan.kind == "now":
        report.plan = TradePlan(kind="none", action=f"WAIT (don't chase the {plan.side.lower()})", side=plan.side,
                                steps=[next((w for w in psych.warnings if w.startswith("Price moved")), psych.warnings[0]),
                                       "Let price pull back. The next analysis (every 15 minutes) will give a fresh entry.",
                                       f"Skipped plan for reference: {plan.side} near {plan.entry_lo:,.0f}-{plan.entry_hi:,.0f}, "
                                       f"stop {plan.stop:,.0f}."])
        report.headline = "Don't chase: wait for a pullback"
        report.bias = "WAIT"
