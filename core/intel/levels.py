"""Key price levels from closed futures candles, in New York time (DST-safe via ZoneInfo)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from core.models import Candle
from core.structure import highs, lows, zigzag

NY = ZoneInfo("America/New_York")
LONDON = (3, 12)     # NY clock hours [start, end)
NEWYORK = (8, 17)


def _ny(t: int) -> datetime:
    return datetime.fromtimestamp(t, timezone.utc).astimezone(NY)


def _roll_day(t: int):
    """Trading day: the NY date of (time + 7h), so the day rolls at 17:00 NY."""
    return (_ny(t).replace(tzinfo=None) + timedelta(hours=7)).date()


def _week_key(t: int):
    d = _roll_day(t)
    return d - timedelta(days=d.weekday())      # weeks start with the Monday trading day (Sunday 17:00 NY)


def _rng(cs):
    return (max(c.h for c in cs), min(c.l for c in cs)) if cs else None


def _session_groups(candles, hours):
    out: dict = {}
    for c in candles:
        n = _ny(c.t)
        if hours[0] <= n.hour < hours[1]:
            out.setdefault(n.date(), []).append(c)
    return out


@dataclass
class Levels:
    daily_open: float | None = None
    weekly_open: float | None = None
    london: tuple | None = None          # (high, low) of the latest London session
    newyork: tuple | None = None
    prev_london: tuple | None = None
    prev_newyork: tuple | None = None
    range_hi: float | None = None
    range_lo: float | None = None
    pd_pct: float | None = None          # 0 = bottom of the 1H dealing range, 100 = top
    pd_zone: str = ""                    # premium | discount | equilibrium


def compute_levels(m15: list[Candle], h1: list[Candle], price: float | None = None) -> Levels:
    """`m15`/`h1` must be CLOSED candles only."""
    L = Levels()
    if m15:
        day, wk = _roll_day(m15[-1].t), _week_key(m15[-1].t)
        L.daily_open = next((c.o for c in m15 if _roll_day(c.t) == day), None)
        L.weekly_open = next((c.o for c in m15 if _week_key(c.t) == wk), None)
        for attr, hours in (("london", LONDON), ("newyork", NEWYORK)):
            g = _session_groups(m15, hours)
            days = sorted(g)
            if days:
                setattr(L, attr, _rng(g[days[-1]]))
                if len(days) > 1:
                    setattr(L, "prev_" + attr, _rng(g[days[-2]]))
    if len(h1) >= 30:
        piv = zigzag(h1, 2.0)
        hs, ls = highs(piv), lows(piv)
        if hs and ls and hs[-1].price > ls[-1].price:
            L.range_hi, L.range_lo = hs[-1].price, ls[-1].price
            p = price if price is not None else (m15[-1].c if m15 else h1[-1].c)
            L.pd_pct = round(max(0.0, min(100.0, (p - L.range_lo) / (L.range_hi - L.range_lo) * 100)), 0)
            L.pd_zone = "premium" if L.pd_pct > 55 else "discount" if L.pd_pct < 45 else "equilibrium"
    return L


def level_lines(L: Levels, sp=lambda x: x) -> list[str]:
    f = lambda v: f"{sp(v):,.0f}"
    out = []
    if L.daily_open is not None:
        out.append(f"Daily open {f(L.daily_open)}" +
                   (f", weekly open {f(L.weekly_open)}" if L.weekly_open is not None else "") + ".")
    for name, v in (("London", L.london), ("New York", L.newyork), ("Previous London", L.prev_london),
                    ("Previous New York", L.prev_newyork)):
        if v:
            out.append(f"{name} session high {f(v[0])}, low {f(v[1])}.")
    if L.pd_zone:
        out.append(f"Price is in the {L.pd_zone} of the 1H range {f(L.range_lo)}-{f(L.range_hi)} "
                   f"({L.pd_pct:.0f}% up the range).")
    return out
