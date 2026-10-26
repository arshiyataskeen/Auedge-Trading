"""Chief analyst: weighted top-down (Daily 40%, 4H 30%, 1H 20%, 15m 10%) + stop-hunt timing.

How it thinks (institutional view):
1. Direction comes from the higher timeframes. A lower timeframe moving the other way is a pullback,
   not a new trend.
2. Price hunts resting stops. In a BUY bias, the best long comes right AFTER sell stops below a low are
   taken (a "hunt") and price closes back up. In a SELL bias, after buy stops above a high are taken.
3. Stops go beyond the hunted liquidity; targets are the next untouched stop pools.
4. Without a fresh hunt or a 15m break in the bias direction, the plan is "wait", with exact levels.
Analysis only: never certainty, never an order.
"""
from __future__ import annotations

from pydantic import BaseModel

from core.indicators import atr
from core.liquidity import Pool, build_stop_map
from core.models import AgentResult, Level, MarketContext
from core.structure import highs, lows, tf_bias

MAX_CONFIDENCE = 85
TFS = [("1d", "Daily", 3, 0.40), ("4h", "4H", 2.5, 0.30), ("1h", "1H", 2, 0.20), ("15m", "15m", 2, 0.10)]
BIAS_NEED = 0.15            # weighted score needed for a directional bias (range -1..+1)
STRONG_POOL = 2.0           # pools at least this strong count as targets


class TFBias(BaseModel):
    tf: str
    bias: str
    text: str
    weight: int             # percent
    role: str = ""          # "trend" | "pullback" | ...


class TradePlan(BaseModel):
    kind: str = "none"      # "now" (a trade) | "watch" (alert only, not a trade) | "none"
    action: str = "NO TRADE"
    side: str | None = None
    entry_lo: float | None = None
    entry_hi: float | None = None
    stop: float | None = None
    be_at: float | None = None   # 1R: take half profit here and move the stop to the entry price
    t1: float | None = None
    t2: float | None = None
    rr1: float | None = None
    rr2: float | None = None
    steps: list[str] = []
    cancel_if: str = ""


class ChiefReport(BaseModel):
    bias: str = "WAIT"
    confidence: int = 0
    confidence_word: str = "Low"
    weighted_score: float = 0
    htf_label: str = ""
    intraday_label: str = ""
    price: float | None = None
    timeframes: list[TFBias] = []
    chips: list[dict] = []
    headline: str = ""
    verdict: str = ""
    buy_zone: list[float] | None = None
    sell_zone: list[float] | None = None
    plan: TradePlan = TradePlan()
    stops_above: list[Pool] = []
    stops_below: list[Pool] = []
    recent_hunt: Pool | None = None
    levels: list[Level] = []
    reasons: list[str] = []
    warnings: list[str] = []
    ai_written: bool = False
    today: dict = {}        # plain "today's trend" summary, filled by today_view()
    day_range: float | None = None   # average daily range (14-day ATR of closed daily candles): how far gold usually moves in a day


def describe(ctx: MarketContext, info: dict) -> str:
    piv, state = info["pivots"], info["state"]
    h, l = highs(piv), lows(piv)
    parts = []
    if state == "DOWN" and h:
        parts.append(f"Downtrend. Lower highs since {ctx.sp(h[-1].price):,.0f}.")
    elif state == "UP" and l:
        parts.append(f"Uptrend. Higher lows since {ctx.sp(l[-1].price):,.0f}.")
    elif h and l:
        parts.append(f"Range {ctx.sp(l[-1].price):,.0f}-{ctx.sp(h[-1].price):,.0f}.")
    if info["recent_bos"]:
        b = info["bos"]
        parts.append(f"Broke {'above' if b[1] == 'UP' else 'below'} {ctx.sp(b[2]):,.0f}.")
    return " ".join(parts) or "Not enough swings yet."


def word_for(score: float) -> str:
    return "BUY" if score >= 0.4 else "BUY lean" if score >= BIAS_NEED else \
        "SELL" if score <= -0.4 else "SELL lean" if score <= -BIAS_NEED else "RANGE"


def fmt(p): return f"{p:,.0f}" if p is not None else "n/a"


def chief(ctx: MarketContext, results: list[AgentResult], weights: dict[str, float],
          data_check: AgentResult | None) -> ChiefReport:
    rep = ChiefReport(price=ctx.spot.price if ctx.spot else None)
    infos, total = {}, 0.0
    for key, name, mult, w in TFS:
        cs = ctx.struct(key)
        if cs and len(cs.candles) >= 60:
            info = tf_bias(cs.candles, mult)
            infos[key] = info
            norm = max(-1.0, min(1.0, info["score"] / 2.5))
            total += w * norm
            rep.timeframes.append(TFBias(tf=name, bias=info["bias"], text=describe(ctx, info), weight=int(w * 100)))
        else:
            rep.timeframes.append(TFBias(tf=name, bias="NO DATA", text="Candles unavailable.", weight=int(w * 100)))
    rep.weighted_score = round(total, 2)
    d1 = ctx.struct("1d")
    if d1 and len(d1.candles) > 16:
        rep.day_range = round(atr(d1.candles[:-1])[-1] or 0, 2) or None     # [:-1]: today's candle is still forming
    direction = 1 if total >= BIAS_NEED else -1 if total <= -BIAS_NEED else 0
    # Roles: a timeframe moving against the weighted direction is a pullback inside it
    for t in rep.timeframes:
        s = 1 if "BUY" in t.bias else -1 if "SELL" in t.bias else 0
        t.role = "with bias" if direction and s == direction else "pullback" if direction and s == -direction else "neutral"

    rep.htf_label = f"BIAS {word_for(total).replace(' lean', ' (lean)')}"
    voters = [r for r in results if r.status == "OK" and weights.get(r.agent, 0) > 0]
    rep.chips = [{"agent": r.agent, "label": r.bias_label or r.bias, "bias": r.bias if r.status == "OK" else "NA"}
                 for r in results]
    total_w = sum(weights[r.agent] * 100 for r in voters) or 1
    net = sum(weights[r.agent] * r.confidence * (1 if r.bias == "BUY" else -1)
              for r in voters if r.bias != "WAIT") / total_w
    n_buy, n_sell = sum(r.bias == "BUY" for r in voters), sum(r.bias == "SELL" for r in voters)
    rep.reasons.append(f"Weighted timeframes (Daily 40%, 4H 30%, 1H 20%, 15m 10%): score {total:+.2f} "
                       f"(needs ±{BIAS_NEED} for a bias).")
    rep.reasons.append(f"Agents: {n_buy} BUY, {n_sell} SELL, {len(voters) - n_buy - n_sell} WAIT (score {net:+.2f}).")
    skipped = [r.agent for r in results if r.status != "OK"]
    if skipped:
        rep.reasons.append("Not counted (no data or error): " + ", ".join(skipped) + ".")
    rep.warnings.append("Analysis only, not financial advice. Prices are indicative; your broker differs by the spread.")

    smap = build_stop_map(ctx)
    rep.stops_above, rep.stops_below, rep.recent_hunt = smap["above"], smap["below"], smap["recent_hunt"]
    a1 = smap["atr1h"] or 5.0
    p = rep.price or smap["price"]
    if rep.recent_hunt:
        h = rep.recent_hunt
        rep.reasons.append(f"Stop hunt {h.hunted_ago_min} min ago: {'sell' if h.side == 'sell' else 'buy'} stops "
                           f"{'below' if h.side == 'sell' else 'above'} {fmt(h.price)} were taken "
                           f"({', '.join(h.sources)}).")

    # Conditional zones: buyers step in after sell stops below are taken, sellers after buy stops above
    near_below = next((x for x in rep.stops_below if x.status == "untouched"), None)
    near_above = next((x for x in rep.stops_above if x.status == "untouched"), None)
    if near_below:
        rep.buy_zone = [round(near_below.price - 0.4 * a1, 2), round(near_below.price, 2)]
    if near_above:
        rep.sell_zone = [round(near_above.price, 2), round(near_above.price + 0.4 * a1, 2)]

    if data_check is None or data_check.veto or data_check.status != "OK":
        rep.bias, rep.confidence, rep.confidence_word = "WAIT", 0, "None"
        rep.intraday_label = "NO TRADE"
        rep.headline = "NO TRADE: data check failed"
        rep.verdict = "Do not trade on this dashboard right now: " + ("; ".join(data_check.warnings[:2]) if data_check and
                       data_check.status == "OK" else "the data check itself could not run")
        rep.plan = TradePlan(kind="none", action="NO TRADE", steps=[rep.verdict])
        return rep

    m15 = infos.get("15m")
    bos15 = m15["bos"] if m15 and m15["recent_bos"] else None
    hunt = rep.recent_hunt
    trigger, why = False, ""
    if direction > 0:
        if hunt and hunt.side == "sell":
            trigger, why = True, f"sell stops below {fmt(hunt.price)} were just hunted"
        elif bos15 and bos15[1] == "UP":
            trigger, why = True, f"15m broke above {fmt(ctx.sp(bos15[2]))}"
    elif direction < 0:
        if hunt and hunt.side == "buy":
            trigger, why = True, f"buy stops above {fmt(hunt.price)} were just hunted"
        elif bos15 and bos15[1] == "DOWN":
            trigger, why = True, f"15m broke below {fmt(ctx.sp(bos15[2]))}"
    agents_agree = direction != 0 and net * direction >= 0

    conf = 35 + abs(total) * 45 + (10 if trigger else 0) + (10 if agents_agree else -10)
    rep.confidence = max(0, min(MAX_CONFIDENCE, int(conf)))
    rep.confidence_word = "High" if rep.confidence >= 70 else "Medium" if rep.confidence >= 50 else "Low"

    if direction == 0:
        rep.bias, rep.intraday_label = "WAIT", "NO TRADE"
        rep.headline = "No clear direction: timeframes cancel out"
        rep.verdict = (f"The weighted timeframes give no direction (score {total:+.2f}). No trade. Watch the stop pools: "
                       f"a hunt of sell stops below {fmt(near_below.price if near_below else None)} then a close back up "
                       f"favours buyers; a hunt of buy stops above {fmt(near_above.price if near_above else None)} then a "
                       f"close back down favours sellers.")
        rep.plan = TradePlan(kind="none", action="NO TRADE", steps=[
            "Do nothing for now: the timeframes disagree.",
            f"Set price alerts at {fmt(near_above.price if near_above else None)} and {fmt(near_below.price if near_below else None)}.",
            "Wait for the next analysis (every 15 minutes)."])
        return rep

    side = "BUY" if direction > 0 else "SELL"
    s = 1 if direction > 0 else -1
    pullbacks = [t.tf for t in rep.timeframes if t.role == "pullback"]
    context = (f"Direction is {side} (weighted {total:+.2f})." +
               (f" {', '.join(pullbacks)} {'is' if len(pullbacks) == 1 else 'are'} moving against it: a pullback, "
                f"not a new trend." if pullbacks else " All timeframes agree."))
    targets_pool = [x for x in (rep.stops_above if s > 0 else rep.stops_below)
                    if x.status == "untouched" and x.strength >= STRONG_POOL]

    if trigger:
        entry = p
        if hunt and ((s > 0 and hunt.side == "sell") or (s < 0 and hunt.side == "buy")):
            stop = hunt.price - s * 0.5 * a1                         # beyond the hunted liquidity
        else:
            guard = near_below if s > 0 else near_above
            stop = (guard.price - s * 0.3 * a1) if guard and abs(p - guard.price) < 2.5 * a1 else p - s * 1.5 * a1
        risk = max(abs(entry - stop), 0.8 * a1)
        stop = entry - s * risk
        t1 = next((x.price for x in targets_pool if abs(x.price - entry) >= 1.2 * risk), entry + s * 1.5 * risk)
        rep.bias = side if agents_agree else "WAIT"
        if rep.bias == side:
            rep.intraday_label = f"{side} NOW"
            rep.headline = f"{side}: bias and trigger aligned"
            # Trade management from the 6-month study: half off at 1R, stop to entry, the rest at target 1.
            be_at = entry + s * risk
            rep.plan = TradePlan(
                kind="now", action=f"{side} NOW", side=side,
                entry_lo=round(entry - 0.15 * a1, 2), entry_hi=round(entry + 0.15 * a1, 2),
                stop=round(stop, 2), be_at=round(be_at, 2), t1=round(t1, 2),
                rr1=round(abs(t1 - entry) / risk, 1),
                steps=[f"{side} between {fmt(entry - 0.15 * a1)} and {fmt(entry + 0.15 * a1)} (current price {fmt(p)}).",
                       f"Put the stop loss at {fmt(stop)} straight away.",
                       f"At {fmt(be_at)} (1R) take half profit and move the stop to your entry price.",
                       f"Take the rest at {fmt(t1)}.",
                       "Risk only 1% of your account (use the size calculator)."],
                cancel_if=f"Do not enter if price is already past {fmt(t1)} or beyond {fmt(stop)}.")
            rep.verdict = (f"{context} Trigger: {why}. {side} near {fmt(p)}, stop {fmt(stop)}, half at {fmt(be_at)}, "
                           f"rest at {fmt(t1)}.")
            rep.levels = [Level(kind="entry", price=round(entry, 2), note="Entry"),
                          Level(kind="stop", price=round(stop, 2), note="Stop loss (beyond the liquidity)"),
                          Level(kind="target", price=round(be_at, 2), note="Half profit at 1R, then stop to entry"),
                          Level(kind="target", price=round(t1, 2), note="Target (next stop pool)")]
            return rep
        why += ", but most agents disagree"

    # Watch alert (not a trade): in the 6-month study, entering these "wait for the hunt" setups lost money.
    # The level is still useful: if the hunt happens, the next analysis usually turns it into a NOW plan.
    pool = near_below if s > 0 else near_above
    if pool:
        entry = pool.price
        rep.plan = TradePlan(
            kind="watch", action=f"WATCH for {side}", side=side, entry_lo=round(min(entry, entry - s * 0.2 * a1), 2),
            entry_hi=round(max(entry, entry - s * 0.2 * a1), 2),
            steps=[f"No trade yet. Set a price alert at {fmt(entry)}.",
                   f"Watch for price to {'dip below' if s > 0 else 'spike above'} {fmt(entry)} "
                   f"({'sell' if s > 0 else 'buy'} stops get hunted there) and a 15m close back "
                   f"{'above' if s > 0 else 'below'} it.",
                   f"If that happens, wait for the next analysis: only a '{side} NOW' plan is a trade."],
            cancel_if="This is an alert, not an entry: entering at the alert lost money in testing.")
        rep.verdict = (f"{context} No entry yet{(' (' + why + ')') if why else ''}. Watch the "
                       f"{'sell' if s > 0 else 'buy'} stops at {fmt(entry)}: a hunt there and a close back "
                       f"{'above' if s > 0 else 'below'} it often sets up the next {side.lower()}.")
    else:
        rep.plan = TradePlan(kind="none", action="WAIT", steps=["No clear stop pool nearby. Wait for the next analysis."])
        rep.verdict = f"{context} No clean setup yet."
    rep.bias, rep.intraday_label = "WAIT", f"WAIT for {side}"
    rep.headline = f"{side} bias, waiting for a stop hunt"
    return rep


def today_view(rep: ChiefReport) -> dict:
    """Plain summary of today's trend from all timeframes (Daily to 15m), with the 15m-analysis levels.
    Only reads the finished report: it does not change the bias or the trade plan."""
    s = rep.weighted_score
    side = "BUY" if s >= BIAS_NEED else "SELL" if s <= -BIAS_NEED else None
    agree = sum((side == "BUY" and "BUY" in t.bias) or (side == "SELL" and "SELL" in t.bias) for t in rep.timeframes)
    strength = "strong" if abs(s) >= 0.4 and agree >= 3 else "weak"
    below = next((x.price for x in rep.stops_below if x.status == "untouched"), None)
    above = next((x.price for x in rep.stops_above if x.status == "untouched"), None)
    tfs = " · ".join(f"{t.tf} {t.bias}" for t in rep.timeframes)
    pullbacks = [t.tf for t in rep.timeframes if t.role == "pullback"]
    if side == "BUY":
        trend = f"UPTREND ({strength})"
        text = (f"Favour BUYS today. Best buys come after a dip below {fmt(below)} (sell stops) and a 15m close back "
                f"above it. Upside magnet: {fmt(above)}. Avoid selling against the trend.")
    elif side == "SELL":
        trend = f"DOWNTREND ({strength})"
        text = (f"Favour SELLS today. Best sells come after a spike above {fmt(above)} (buy stops) and a 15m close back "
                f"below it. Downside magnet: {fmt(below)}. Avoid buying against the trend.")
    else:
        trend = "NO CLEAR TREND"
        text = (f"Timeframes disagree today: expect a range between about {fmt(below)} and {fmt(above)}. Best to stay "
                f"out, or wait for a 15m close outside that range.")
    if side and pullbacks:
        text += f" {', '.join(pullbacks)} {'is' if len(pullbacks) == 1 else 'are'} pulling back against it right now."
    if rep.headline.startswith("NO TRADE: data check"):
        text += " Right now: do not trade (data check failed or market closed)."
    else:
        text += f" Right now: {rep.plan.action}."
    return {"side": side, "trend": trend, "tfs": tfs, "text": text, "buy_below": below, "sell_above": above}
