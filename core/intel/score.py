"""Setup quality: a 0-100 factor score with a per-factor breakdown, a band and an AVOID label.

This is a checklist score, NOT a probability of winning. Weights live in data/intel_weights.json (defaults below).
Each factor is ok=True (full weight), ok=False (none) or ok=None (not available: half weight, neutral).
Every intel module import is optional: a missing module shows "not available" and counts neutral.
Only `build_quality` touches market data; `score_factors` is pure.
"""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "data" / "intel_weights.json"

DEFAULT_WEIGHTS = {"align": 20, "sweep_bos": 15, "retest": 10, "displacement": 10, "zones": 10,
                   "session": 10, "news": 10, "volatility": 10, "entry": 5, "spread": 0}
DEFAULT_BANDS = {"strong": 85, "good": 70, "fair": 55}
LABELS = {"align": "1H and 15m alignment", "sweep_bos": "Stop hunt then break", "retest": "5-minute break and retest",
          "displacement": "Strong push candle", "zones": "Gap / order block nearby", "session": "Trading session",
          "news": "News risk", "volatility": "Volatility", "entry": "Entry timing and room", "spread": "Spread"}
NA = "not available"


def load_config(path: Path | None = None) -> dict:
    w, b = dict(DEFAULT_WEIGHTS), dict(DEFAULT_BANDS)
    try:
        d = json.loads((path or PATH).read_text(encoding="utf-8"))
        w.update({k: float(v) for k, v in (d.get("weights") or {}).items() if k in w})
        b.update({k: float(v) for k, v in (d.get("bands") or {}).items() if k in b})
    except Exception:  # noqa: BLE001 - missing/bad file: defaults
        pass
    return {"weights": w, "bands": b}


def band(score: float, bands: dict) -> str:
    return "strong" if score >= bands["strong"] else "good" if score >= bands["good"] else \
        "fair" if score >= bands["fair"] else "weak"


def score_factors(factors: dict, blocks: list[str] | None = None, config: dict | None = None) -> dict:
    """factors: {name: {"ok": bool|None, "text": str}}. blocks: plain reasons of gates that fired."""
    cfg = config or load_config()
    w, bands = cfg["weights"], cfg["bands"]
    tot = got = 0.0
    rows = []
    for name, wt in w.items():
        f = factors.get(name) or {"ok": None, "text": NA}
        credit = 1.0 if f["ok"] is True else 0.0 if f["ok"] is False else 0.5
        tot += wt
        got += wt * credit
        rows.append({"name": name, "label": LABELS.get(name, name), "ok": f["ok"], "weight": wt,
                     "points": round(wt * credit, 1), "text": f.get("text") or NA})
    sc = int(round(100 * got / tot)) if tot else 0
    blocks = list(blocks or [])
    avoid = bool(blocks) or sc < bands["fair"]
    why = blocks[:] if blocks else ([f"Setup quality {sc}/100 is below {bands['fair']:.0f}."] if avoid else [])
    bd = band(sc, bands)
    text = (f"Setup quality {sc}/100 ({bd}). This is a checklist score, not a chance of winning."
            + (" AVOID: " + " ".join(why) if avoid else ""))
    return {"score": sc, "band": bd, "bands": bands, "avoid": avoid, "label": "AVOID" if avoid else "",
            "avoid_reasons": why, "blocks": blocks, "factors": rows, "text": text}


# ---------------------------------------------------------------- data -> factors (all optional, never raises)
def _f(ok, text):
    return {"ok": ok, "text": text}


def _closed(ctx, tf):
    try:
        cs = ctx.struct(tf)
        return cs.closed() if cs else []
    except Exception:  # noqa: BLE001
        return []


def _displacement(c15, side):
    from core.indicators import atr
    if len(c15) < 20:
        return _f(None, NA)
    a = atr(c15)[-1] or 0
    s = 1 if side == "BUY" else -1
    for c in c15[-3:]:
        rng = c.h - c.l
        if a and rng >= 1.2 * a and abs(c.c - c.o) >= 0.6 * rng and (c.c - c.o) * s > 0:
            return _f(True, f"A strong {'up' if s > 0 else 'down'} candle in the last 45 minutes backs the move.")
    return _f(False, "No strong push candle in the trade's direction recently.")


def build_quality(ctx, rep, side: str, plan: dict | None = None, flag=None) -> tuple[dict, list[str]]:
    """Return (quality dict, reasons that should block the trade under the flags that are ON)."""
    if flag is None:
        try:
            from core.intel.flags import flag
        except Exception:  # noqa: BLE001
            def flag(_n):
                return False
    T = ctx.generated_at.timestamp()
    c15 = _closed(ctx, "15m")
    F, gates, flag_blocks = {}, [], []

    al = (rep.intel or {}).get("align") or {}
    st = al.get("state")
    if st:
        want = "aligned_up" if side == "BUY" else "aligned_down"
        F["align"] = _f(st == want, al.get("text") or st)
    # sweep -> candle-close break of structure (15m, closed candles): see core/intel/structure_q.py
    try:
        from core.intel.structure_q import analyze
        sq = analyze(c15, side)
        F["sweep_bos"] = _f(sq.ok, sq.text) if len(c15) >= 30 else _f(None, NA)
    except Exception:  # noqa: BLE001
        pass
    try:
        from core.newsintel.m5 import m5_confirmations
        c5 = _closed(ctx, "5m")
        if c5:
            m = m5_confirmations(c5)
            F["retest"] = _f(m.get("retest") == ("up" if side == "BUY" else "down"), m.get("text") or NA)
    except Exception:  # noqa: BLE001
        pass
    try:
        F["displacement"] = _displacement(c15, side)
    except Exception:  # noqa: BLE001
        pass
    try:
        from core.intel.zones import find_zones
        zs = find_zones(c15, price=rep.price)
        want = "bull" if side == "BUY" else "bear"
        near = [z for z in zs.near if z.side == want]
        F["zones"] = _f(bool(near), near[0].text if near else "No gap or order block on the trade's side near price.")
    except Exception:  # noqa: BLE001
        pass
    try:
        from core.intel.sessions import current_sessions
        sn = current_sessions(T)
        F["session"] = _f(None, sn.text) if sn.closed else _f(not sn.low_liquidity and bool(sn.sessions), sn.text)
        if sn.low_liquidity:
            gates.append(("SESSION", sn.text, True))
    except Exception:  # noqa: BLE001
        pass
    try:
        news_ev = None
        try:
            from core.newsintel.gates import blackout
            news_ev = blackout(T)
        except Exception:  # noqa: BLE001
            news_ev = None
        extra = None
        try:
            from core.intel.news_extra import extra_blackout
            extra = extra_blackout(T)
        except Exception:  # noqa: BLE001
            extra = None
        ev = news_ev or extra
        nm = (ev or {}).get("name") or (ev or {}).get("kind") or "a news release"
        F["news"] = _f(ev is None, "No big news release in the next or last 30 minutes." if ev is None
                       else f"Inside the no-trade window of {nm}.")
        if news_ev:
            gates.append(("NEWS", f"News window: {nm}.", False))      # already enforced by the live/backtest news gate
        if extra:
            gates.append(("NEWS_EXTRA", f"News window: {nm}.", False))
    except Exception:  # noqa: BLE001
        pass
    try:
        from core.intel.volatility import regime, stop_check
        vr = regime(c15)
        if vr.regime != "unknown":
            F["volatility"] = _f(vr.regime in ("normal", "high"), vr.text)
            if vr.regime == "abnormal":
                gates.append(("VOL", vr.text, False))
        if plan and plan.get("stop") is not None:
            sc = stop_check(plan, c15)
            if not sc.ok:
                gates.append(("VOL", sc.text, False))
    except Exception:  # noqa: BLE001
        pass
    if plan and plan.get("t1") is not None:
        try:
            from core.intel.entry import check_entry
            er = check_entry(plan, c15, {"above": rep.stops_above, "below": rep.stops_below})
            F["entry"] = _f(er.ok, er.text)
        except Exception:  # noqa: BLE001
            pass
    F["spread"] = _f(None, "Spread not measured here (counted as neutral).")

    blocking = []
    for name, text, soft in gates:
        if name == "SESSION":
            continue                         # judged against the score below
        blocking.append(text)
    q = score_factors(F, blocking)
    for name, text, soft in gates:
        if name == "SESSION" and q["score"] < 70:
            q["blocks"].append(text)
            q["avoid"], q["label"] = True, "AVOID"
            if text not in q["avoid_reasons"]:
                q["avoid_reasons"].append(text)
    # what the flags that are ON turn into a WAIT
    for name, text, soft in gates:
        if name == "SESSION":
            if flag("SESSION") and q["score"] < 70:
                flag_blocks.append(text)
        elif name in ("VOL", "NEWS_EXTRA") and flag(name):
            flag_blocks.append(text)
    if flag("SWEEP_BOS") and not ((F.get("sweep_bos") or {}).get("ok") or (F.get("retest") or {}).get("ok")):
        flag_blocks.append("No stop hunt + break and no 5-minute break + retest.")
    if flag("ENTRY") and (F.get("entry") or {}).get("ok") is False:
        flag_blocks.append(F["entry"]["text"])
    if flag("SCORE_GATE") and q["avoid"]:
        flag_blocks.append(" ".join(q["avoid_reasons"]) or "Setup quality too low.")
    q["flags_on"] = [n for n in ("ALIGN", "SWEEP_BOS", "SESSION", "VOL", "ENTRY", "NEWS_EXTRA", "SCORE_GATE") if flag(n)]
    return q, flag_blocks
