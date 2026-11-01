"""Trade reviewer: after every finished trade, who suggested it, what happened, and (for losses) why it went wrong.

Sources: live demo trades (track.db trades + the analysis snapshot saved when each was decided) and the newest
backtest result (its trades + steps), so there is enough evidence long before the demo has many trades.

Per trade:  for / against / waiting agents, outcome, and loss reasons:
  news        a high-impact news window fell inside the trade
  hunted      stopped out, then price came back to the entry within 3 h (stop too tight / stop hunt)
  fast        stopped within 1 h of the entry (chased or badly timed entry)
  trend       traded against today's trend
  weak        thin agreement (Chief confidence < 55 or fewer than 3 agents for it)
  no_follow   expired after 24 h without reaching the target
Scorecard:  per agent, how often its vote helped (for a winner / against a loser) or hurt.
Tuning:     never from single trades. An agent that keeps hurting (>= 15 decisive trades, < 40% helped) asks the
            weekly review board to run early; the board backtests 6 months and changes votes only if proven better.
data/trade_reviews.json holds the result.
"""
from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "trade_reviews.json"
CACHE = DATA / "backtest_cache" / "fut_15m.json"
MIN_DECISIVE = 15
WEAK_BELOW, STRONG_FROM = 0.40, 0.60
EARLY_REVIEW_AFTER_S = 3 * 86400      # an early board run at most every 3 days

WIN_TEXT = {
    "with_trend": "traded with today's trend",
    "strong": "strong agreement (confidence 65+, 4+ agents for it)",
    "quick": "reached the target within 4 hours",
    "protected": "half taken at 1R, so the rest ran risk-free",
}
REASON_TEXT = {
    "news": "a big news release hit during the trade",
    "hunted": "the stop was taken, then price came back to the entry (stop too tight or hunted)",
    "fast": "stopped within an hour (entry was chased or badly timed)",
    "trend": "the trade went against today's trend",
    "weak": "only weak agreement behind the trade",
    "no_follow": "no follow-through: it expired without reaching the target",
}
LESSON = {
    "news": "Several losses came around news. The news filter windows may be too short.",
    "hunted": "Several stops were hunted and price came back. Stops may sit too close to obvious levels.",
    "fast": "Several trades failed within an hour. Entries may be chasing the move.",
    "trend": "Several losses were against today's trend. Counter-trend trades are not paying.",
    "weak": "Several losses had weak agreement. Low-confidence NOW calls are not paying.",
    "no_follow": "Several trades went nowhere. Targets may be too far for the day's range.",
}


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing or half-written
        return default


def _candles(extra: list[dict] | None = None) -> list[dict]:
    """Futures 15m candles: the saved history plus any fresher live ones, sorted by time."""
    by_t = {p["t"]: p for p in _read(CACHE, {}).get("points", []) if None not in (p.get("h"), p.get("l"))}
    for c in extra or []:
        by_t[c["t"]] = c
    return [by_t[t] for t in sorted(by_t)]


def _news_in(a: float, b: float) -> list[str]:
    try:
        from . import news
        return [e.get("name", "news") for e in news.events() if e.get("blocks") and a - 1800 <= e["t"] <= b]
    except Exception:  # noqa: BLE001 - no news data: just skip this reason
        return []


def review(t: dict, snap: dict | None, candles: list[dict]) -> dict:
    """One trade (futures prices: entry, stop, t1, exit; times entry_t, exit_t) -> its review."""
    side, s = t["side"], (1 if t["side"] == "BUY" else -1)
    ag = (snap or {}).get("ag") or []
    pro = [a[0] for a in ag if a[1] == side]
    con = [a[0] for a in ag if a[1] in ("BUY", "SELL") and a[1] != side]
    won = (t.get("r") or 0) > 0
    why = t.get("why") or ""
    tr, cf = (snap or {}).get("tr", ""), (snap or {}).get("cf") or 0
    news_hit = bool(_news_in(t["entry_t"], t["exit_t"]))
    h = time.gmtime(t["entry_t"]).tm_hour
    tags = {                                  # the conditions of every trade, won or lost, for the "what wins" table
        "trend": ("with" if (side == "BUY" and "UPTREND" in tr) or (side == "SELL" and "DOWNTREND" in tr)
                  else "against" if ("UPTREND" in tr or "DOWNTREND" in tr) else "none"),
        "agreement": "strong" if cf >= 65 and len(pro) >= 4 else "weak" if cf < 55 or len(pro) < 3 else "normal",
        "session": "Asia" if h < 7 else "London" if h < 12 else "New York" if h < 21 else "late",
        "news": "yes" if news_hit else "no",
    }
    reasons: list[str] = []
    if won:                                   # why it worked
        reasons += [k for k, ok in (("with_trend", tags["trend"] == "with"), ("strong", tags["agreement"] == "strong"),
                                    ("quick", t["exit_t"] - t["entry_t"] <= 4 * 3600 and why.startswith("target")),
                                    ("protected", "after half" in why)) if ok]
    else:
        if news_hit:
            reasons.append("news")
        stopped = why.startswith("stop") or why.startswith("breakeven")
        if stopped and why.startswith("stop"):
            after = [c for c in candles if t["exit_t"] <= c["t"] < t["exit_t"] + 3 * 3600]
            if any((c["l"] <= t["entry"]) if s < 0 else (c["h"] >= t["entry"]) for c in after):
                reasons.append("hunted")
            if t["exit_t"] - t["entry_t"] <= 3600:
                reasons.append("fast")
        if tags["trend"] == "against":
            reasons.append("trend")
        if tags["agreement"] == "weak":
            reasons.append("weak")
        if why.startswith("expired"):
            reasons.append("no_follow")
    return {"t": int(t["entry_t"]), "side": side, "r": round(t.get("r") or 0, 2), "usd": t.get("usd"), "won": won,
            "why": why, "for": pro, "against": con, "reasons": reasons, "tags": tags, "src": t.get("src", "backtest")}


def _live_trades() -> list[dict]:
    """Closed demo trades in futures prices (+ the snapshot of the analysis that opened each)."""
    out = []
    try:
        con = sqlite3.connect(DATA / "track.db")
        rows = con.execute("SELECT ts, side, entry, stop, t1, gap, closed_ts, exit_price, result_r, usd, why, cost "
                           "FROM trades WHERE status != 'open' AND closed_ts IS NOT NULL").fetchall()
        recs = con.execute("SELECT ts, snap FROM recs WHERE snap IS NOT NULL ORDER BY ts").fetchall()
        con.close()
    except Exception:  # noqa: BLE001 - no live record yet
        return out
    for ts, side, entry, stop, t1, gap, cts, exit_px, r, usd, why, cost in rows:
        gap = gap or 0
        snap = None
        for rts, raw in recs:                     # the analysis that opened it: the last one at or before the entry
            if rts <= ts + 5:
                snap = raw
            else:
                break
        out.append(({"side": side, "entry_t": ts, "exit_t": cts, "entry": entry + gap, "stop": stop + gap,
                     "t1": t1 + gap, "exit": (exit_px or entry) + gap, "r": r, "usd": usd, "why": why, "src": "live"},
                    json.loads(snap) if snap else None))
    return out


def _backtest_trades() -> tuple[str | None, list]:
    """The backtest with the most trades (more evidence); newest first on a tie."""
    best, best_d = None, None
    for f in sorted((DATA / "backtests").glob("bt_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        d = _read(f, {})
        if d.get("trades") and d.get("steps") and (best_d is None or len(d["trades"]) > len(best_d["trades"])):
            best, best_d = f, d
    if not best:
        return None, []
    steps = {st["t"]: st for st in best_d["steps"]}
    return best.stem, [({**t, "src": "backtest"}, steps.get(t["decided_t"])) for t in best_d["trades"]]


def scorecard(reviews: list[dict]) -> list[dict]:
    help_, hurt = Counter(), Counter()
    for rv in reviews:
        for a in rv["for"]:
            (help_ if rv["won"] else hurt)[a] += 1
        for a in rv["against"]:
            (hurt if rv["won"] else help_)[a] += 1
    rows = []
    for a in sorted(set(help_) | set(hurt)):
        n = help_[a] + hurt[a]
        acc = help_[a] / n if n else 0
        verdict = ("weak" if acc < WEAK_BELOW else "strong" if acc >= STRONG_FROM else "ok") if n >= MIN_DECISIVE else "few trades"
        rows.append({"agent": a, "helped": help_[a], "hurt": hurt[a], "n": n, "acc": round(acc, 3), "verdict": verdict})
    return sorted(rows, key=lambda x: -x["acc"])


def lessons(reviews: list[dict]) -> list[str]:
    losses = [rv for rv in reviews if not rv["won"]][-20:]
    if len(losses) < 4:
        return []
    c = Counter(r for rv in losses for r in rv["reasons"])
    return [f"{LESSON[k]} ({n} of the last {len(losses)} losses)" for k, n in c.most_common() if n / len(losses) >= 0.35]


def conditions(reviews: list[dict]) -> list[dict]:
    """Win rate and average R per condition (e.g. trend = with / against): what our winners have in common."""
    rows = []
    for key in ("trend", "agreement", "session", "news"):
        for val in sorted({rv["tags"][key] for rv in reviews}):
            g = [rv for rv in reviews if rv["tags"][key] == val]
            rows.append({"cond": key, "val": val, "n": len(g), "win": round(sum(rv["won"] for rv in g) / len(g), 3),
                         "avg_r": round(sum(rv["r"] for rv in g) / len(g), 2), "total_r": round(sum(rv["r"] for rv in g), 2)})
    return rows


def win_patterns(reviews: list[dict]) -> list[str]:
    wins = [rv for rv in reviews if rv["won"]][-30:]
    if len(wins) < 4:
        return []
    c = Counter(r for rv in wins for r in rv["reasons"])
    return [f"{WIN_TEXT[k][0].upper() + WIN_TEXT[k][1:]} in {n} of the last {len(wins)} wins" for k, n in c.most_common()
            if n / len(wins) >= 0.35]


def run(live_candles: list[dict] | None = None) -> dict:
    """Review every finished trade, update the scorecard and lessons, and save data/trade_reviews.json."""
    candles = _candles(live_candles)
    live_pairs = _live_trades()
    live = [review(t, sn, candles) for t, sn in live_pairs]
    bt_id, bt = _backtest_trades()
    hist = [review(t, sn, candles) for t, sn in bt]
    from . import dataset             # archive: every reviewed trade, never overwritten
    dataset.record_trades("live", None, live, [t for t, _ in live_pairs])
    if bt_id:
        dataset.record_trades("backtest", bt_id, hist, [t for t, _ in bt])
    allr = sorted(hist + live, key=lambda x: x["t"])
    prev = _read(OUT, {})
    out = {"made_at": time.time(), "backtest": bt_id, "n_live": len(live), "n_backtest": len(hist),
           "live": live[-30:][::-1], "recent_backtest": hist[-15:][::-1], "agents": scorecard(allr),
           "lessons": lessons(allr), "win_patterns": win_patterns(allr), "conditions": conditions(allr), "reasons": dict(Counter(r for rv in allr if not rv["won"] for r in rv["reasons"])),
           "early_review_at": prev.get("early_review_at", 0)}
    DATA.mkdir(exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1), encoding="utf-8")
    tmp.replace(OUT)
    return out


def weak_voters(result: dict, voting_off: list[str]) -> list[str]:
    return [a["agent"] for a in result.get("agents", []) if a["verdict"] == "weak" and a["agent"] not in voting_off]


def mark_early_review() -> None:
    d = _read(OUT, {})
    d["early_review_at"] = time.time()
    OUT.write_text(json.dumps(d, indent=1), encoding="utf-8")


def latest() -> dict:
    return _read(OUT, {})


def due_early_review(result: dict, voting_off: list[str]) -> bool:
    return bool(weak_voters(result, voting_off)) and time.time() - result.get("early_review_at", 0) > EARLY_REVIEW_AFTER_S
