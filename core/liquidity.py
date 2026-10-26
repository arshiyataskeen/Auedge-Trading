"""Stop-loss map: where stops are likely resting, and whether they were just hunted.

Institutional view: price is drawn to pools of resting stops. Buy stops sit ABOVE highs (shorts' stops,
breakout buyers); sell stops sit BELOW lows (longs' stops, breakout sellers). The more obvious the level,
the more stops: equal highs/lows, swing points on higher timeframes, previous day/week high/low, the
Asian session range and round numbers.

Status of each level, judged only on candles AFTER the level formed:
- untouched: price never traded through it -> stops still resting there (a magnet)
- hunted:    price wicked through but no candle closed beyond -> stops were taken (often before a reversal)
- broken:    a candle closed beyond -> the level became a breakout; it no longer holds stops (dropped)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from .indicators import atr
from .structure import confirmed, zigzag

TF_WEIGHT = {"1d": 3.0, "4h": 2.0, "1h": 1.5, "15m": 1.0}
TF_SEC = {"1d": 86400, "4h": 14400, "1h": 3600, "15m": 900}
HUNT_RECENT_MIN = 240          # a hunt in the last 4 hours counts as "fresh"


class Pool(BaseModel):
    price: float               # spot price (converted from futures)
    side: str                  # "buy" = buy stops above highs, "sell" = sell stops below lows
    strength: float            # bigger = more obvious level = more stops
    sources: list[str]
    status: str = "untouched"  # untouched | hunted
    hunted_ago_min: int | None = None


def _status(candles, lvl: float, side: str):
    """(status, pierce_time) over the candles given (all formed after the level)."""
    pierce_t = None
    for c in candles:
        if side == "buy":
            if c.c > lvl:
                return "broken", c.t
            if c.h > lvl:
                pierce_t = c.t
        else:
            if c.c < lvl:
                return "broken", c.t
            if c.l < lvl:
                pierce_t = c.t
    return ("hunted", pierce_t) if pierce_t else ("untouched", None)


def build_stop_map(ctx) -> dict:
    d, h4, h1, m15 = (ctx.struct(k) for k in ("1d", "4h", "1h", "15m"))
    if not all(cs and len(cs.candles) > 60 for cs in (d, h4, h1, m15)):
        return {"above": [], "below": [], "recent_hunt": None, "atr1h": None, "price": None}
    now = ctx.generated_at.astimezone(timezone.utc)
    now_s = now.timestamp()
    price = m15.candles[-1].c                       # futures terms; converted at the end
    a1 = atr(h1.candles)[-1] or 1.0
    levels: list[dict] = []                         # {p, side, w, src, status, t}

    def add(p, side, w, src, after_candles):
        st, t = _status(after_candles, p, side)
        if st != "broken":
            levels.append({"p": p, "side": side, "w": w, "src": src, "status": st, "t": t})

    # 1) Swing highs/lows on each timeframe (+ equal highs/lows = double tops/bottoms)
    for key, cs, mult in (("1d", d, 3), ("4h", h4, 2.5), ("1h", h1, 2), ("15m", m15, 2)):
        cl = cs.candles
        piv = confirmed(zigzag(cl, mult))[-14:]
        for p in piv:
            side = "buy" if p.kind == "H" else "sell"
            add(p.price, side, TF_WEIGHT[key], f"{key} swing {'high' if side == 'buy' else 'low'}", cl[p.i + 1:])
        tol = 0.15 * (atr(cl)[-1] or a1)
        for kind, side, name in (("H", "buy", "equal highs"), ("L", "sell", "equal lows")):
            pts = [p for p in piv if p.kind == kind]
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    if abs(pts[i].price - pts[j].price) <= tol:
                        lvl = max(pts[i].price, pts[j].price) if side == "buy" else min(pts[i].price, pts[j].price)
                        add(lvl, side, 2.0 + TF_WEIGHT[key] / 2, f"{key} {name}", cl[max(pts[i].i, pts[j].i) + 1:])

    # 2) Previous day and previous week high/low (checked on 15m candles since today / this week began)
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since_day = [c for c in m15.candles if c.t >= day0.timestamp()]
    pd = d.candles[-2]
    add(pd.h, "buy", 2.5, "previous day high", since_day)
    add(pd.l, "sell", 2.5, "previous day low", since_day)
    week0 = (day0 - timedelta(days=day0.weekday())).timestamp()
    prev_week = [c for c in d.candles if week0 - 7 * 86400 <= c.t < week0]
    if prev_week:
        since_week = [c for c in d.candles if c.t >= week0][:-1] + since_day
        add(max(c.h for c in prev_week), "buy", 3.0, "previous week high", since_week)
        add(min(c.l for c in prev_week), "sell", 3.0, "previous week low", since_week)

    # 3) Asian session range (00:00-07:00 UTC), checked on candles after 07:00
    asia = [c for c in since_day if c.t < day0.timestamp() + 7 * 3600]
    if asia and now.hour >= 7:
        after = [c for c in since_day if c.t >= day0.timestamp() + 7 * 3600]
        add(max(c.h for c in asia), "buy", 1.5, "Asian session high", after)
        add(min(c.l for c in asia), "sell", 1.5, "Asian session low", after)

    # 4) Round numbers every $50 (in SPOT terms), checked on the last 8 hours
    gap = ctx.futures_gap or 0
    last8h = [c for c in m15.candles if c.t >= now_s - 8 * 3600]
    base = round((price - gap) / 50) * 50
    for k in range(-3, 4):
        lvl = base + 50 * k + gap
        if abs(lvl - price) > 0.2 * a1:
            add(float(lvl), "buy" if lvl > price else "sell", 1.0, f"round number {base + 50 * k:,.0f}", last8h)

    # Right side of price only, within ~3%
    levels = [L for L in levels if abs(L["p"] - price) / price < 0.03 and
              ((L["side"] == "buy" and L["p"] > price) or (L["side"] == "sell" and L["p"] < price))]

    # Merge levels within 0.35 x 1H ATR into one pool (confluence = more stops)
    levels.sort(key=lambda L: L["p"])
    pools_raw: list[dict] = []
    for L in levels:
        last = pools_raw[-1] if pools_raw else None
        if last and L["side"] == last["side"] and L["p"] - last["hi"] <= 0.35 * a1:
            last["hi"] = L["p"]; last["ps"].append(L["p"]); last["src"].append(L["src"])
            last["w"] += 0.7 * L["w"]
            if L["status"] == "hunted" and (last["t"] is None or (L["t"] or 0) > last["t"]):
                last["t"] = L["t"]
        else:
            pools_raw.append({"hi": L["p"], "ps": [L["p"]], "side": L["side"], "w": L["w"], "src": [L["src"]],
                              "t": L["t"] if L["status"] == "hunted" else None})

    pools = []
    for m in pools_raw:
        lvl = max(m["ps"]) if m["side"] == "buy" else min(m["ps"])
        ago = int((now_s - m["t"]) / 60) if m["t"] else None
        pools.append(Pool(price=ctx.sp(lvl), side=m["side"], strength=round(m["w"], 1),
                          sources=sorted(set(m["src"])), status="hunted" if m["t"] else "untouched",
                          hunted_ago_min=ago))
    above = sorted([p for p in pools if p.side == "buy"], key=lambda p: p.price)
    below = sorted([p for p in pools if p.side == "sell"], key=lambda p: -p.price)
    fresh = [p for p in pools if p.hunted_ago_min is not None and p.hunted_ago_min <= HUNT_RECENT_MIN]
    return {"above": above[:6], "below": below[:6],
            "recent_hunt": min(fresh, key=lambda p: p.hunted_ago_min) if fresh else None,
            "atr1h": a1, "price": ctx.sp(price)}
