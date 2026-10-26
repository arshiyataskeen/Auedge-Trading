"""One compact record of an analysis step, saved live (track.db) and in backtests, for the Calendar tab.

Fields: t time, p price, a plan action, k plan kind, sd side, cf Chief confidence, sc weighted score, tr today's trend,
lv plan levels [entry_lo, entry_hi, stop, half-at-1R, target], up / dn nearest untouched stop pools above / below,
ag agents [[name, bias, confidence, outcome]] where outcome is filled in later ("hit" / "miss" / "flat" after 4 hours).
"""
from __future__ import annotations


def snap(t: float, price: float, results, rep) -> dict:
    p = rep.plan
    return {
        "t": int(t), "p": round(price, 2), "a": p.action, "k": p.kind, "sd": p.side, "cf": rep.confidence,
        "sc": rep.weighted_score, "tr": (rep.today or {}).get("trend", ""),
        "lv": [p.entry_lo, p.entry_hi, p.stop, p.be_at, p.t1],
        "up": [x.price for x in rep.stops_above if x.status == "untouched"][:3],
        "dn": [x.price for x in rep.stops_below if x.status == "untouched"][:3],
        "ag": [[r.agent, r.bias, r.confidence, None] for r in results if r.status == "OK"],
    }
