"""Track record: saves every suggestion and scores it later against what price actually did.

- Agent calls (BUY/SELL): scored 4 hours later. Hit = price moved at least $3 their way; miss = at least
  $3 against; smaller moves are "flat" and not counted.
- Chief trades (only "BUY NOW"/"SELL NOW" plans): half comes off at 1R and the rest's stop moves to the entry;
  the rest closes at target 1 or at the entry. Lost if the stop is reached before 1R (if one candle touches both,
  it counts as lost), expired after 24 hours.
Prices are evaluated on gold futures 15m candles (real high/low) shifted by the futures-spot gap saved at
the time of the call. Stored in data/track.db (SQLite) next to the app.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "track.db"
HORIZON_S = 4 * 3600
MOVE_MIN = 3.0                 # dollars
TRADE_EXPIRY_S = 24 * 3600
MIN_GAP_S = 10 * 60            # do not record the same agent twice within 10 minutes (Refresh button)
# Demo account: every "NOW" plan that passes the Discipline rules becomes a demo position (no real broker).
DEMO_ACCOUNT = 25000.0         # starting balance, dollars
DEMO_LOT = 0.1                 # fixed lot: 0.1 = 10 oz = $10 per $1 move
DEMO_COST = 0.30               # spread/slippage per side, dollars per oz (same as the backtest)


def _db() -> sqlite3.Connection:
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY, ts REAL, agent TEXT, bias TEXT, confidence INTEGER,
            price_spot REAL, price_fut REAL, outcome TEXT, move REAL);
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY, ts REAL, side TEXT, entry REAL, stop REAL, t1 REAL, t2 REAL, gap REAL,
            status TEXT DEFAULT 'open', closed_ts REAL, result_r REAL);
        CREATE TABLE IF NOT EXISTS recs (
            id INTEGER PRIMARY KEY, ts REAL, side TEXT, trend TEXT, action TEXT, price_spot REAL, price_fut REAL,
            outcome TEXT, move REAL, against REAL);
    """)
    have = {r[1] for r in con.execute("PRAGMA table_info(trades)")}
    for col, typ in (("lot", "REAL"), ("cost", "REAL"), ("half", "INTEGER DEFAULT 0"), ("exit_price", "REAL"),
                     ("usd", "REAL"), ("why", "TEXT"), ("journal_id", "INTEGER")):
        if col not in have:                      # older databases: add the demo-account columns
            con.execute(f"ALTER TABLE trades ADD COLUMN {col} {typ}")
    if "snap" not in {r[1] for r in con.execute("PRAGMA table_info(recs)")}:
        con.execute("ALTER TABLE recs ADD COLUMN snap TEXT")      # full analysis snapshot for the Calendar tab
    return con


def record(ctx, results, report) -> None:
    """Save this analysis' directional calls and any 'NOW' trade plan."""
    fut = ctx.struct("15m")
    if not ctx.spot or not fut or not fut.candles:
        return
    now = time.time()
    p_spot, p_fut = ctx.spot.price, fut.candles[-1].c
    with _db() as con:
        calls = [(r.agent, r.bias, r.confidence) for r in results if r.status == "OK" and r.bias in ("BUY", "SELL")]
        direction = "BUY" if report.weighted_score >= 0.15 else "SELL" if report.weighted_score <= -0.15 else None
        if direction:
            calls.append(("chief", direction, report.confidence))
        for agent, bias, conf in calls:
            last = con.execute("SELECT ts FROM calls WHERE agent=? ORDER BY ts DESC LIMIT 1", (agent,)).fetchone()
            if last and now - last[0] < MIN_GAP_S:
                continue
            con.execute("INSERT INTO calls (ts, agent, bias, confidence, price_spot, price_fut) VALUES (?,?,?,?,?,?)",
                        (now, agent, bias, conf, p_spot, p_fut))
        # Every recommendation (today's trend + the plan's action), for the "Our calls vs what happened" list
        last = con.execute("SELECT ts FROM recs ORDER BY ts DESC LIMIT 1").fetchone()
        if not last or now - last[0] >= MIN_GAP_S:
            import json
            from .snapshot import snap
            td = report.today or {}
            con.execute("INSERT INTO recs (ts, side, trend, action, price_spot, price_fut, snap) VALUES (?,?,?,?,?,?,?)",
                        (now, td.get("side"), td.get("trend", ""), report.plan.action, p_spot, p_fut,
                         json.dumps(snap(now, p_spot, results, report))))
        plan = report.plan
        if plan.kind == "now" and plan.stop and plan.t1 and ctx.futures_gap is not None:
            open_same = con.execute("SELECT 1 FROM trades WHERE status='open' AND side=?", (plan.side,)).fetchone()
            if not open_same:                    # demo order: filled at the price plus the cost
                fill = p_spot + (DEMO_COST if plan.side == "BUY" else -DEMO_COST)
                con.execute("INSERT INTO trades (ts, side, entry, stop, t1, t2, gap, lot, cost) VALUES (?,?,?,?,?,?,?,?,?)",
                            (now, plan.side, round(fill, 2), plan.stop, plan.t1, plan.t2, ctx.futures_gap or 0,
                             DEMO_LOT, DEMO_COST))


def evaluate(ctx) -> None:
    """Score calls older than 4 hours and settle open trades, using futures 15m candles."""
    fut = ctx.struct("15m")
    if not fut or not fut.candles:
        return
    cl = fut.candles
    now = time.time()
    with _db() as con:
        for cid, ts, bias, p_fut in con.execute(
                "SELECT id, ts, bias, price_fut FROM calls WHERE outcome IS NULL AND ts <= ?", (now - HORIZON_S,)).fetchall():
            later = [c for c in cl if c.t >= ts + HORIZON_S - 900]
            if not later or cl[0].t > ts:
                if now - ts > 5 * 86400:
                    con.execute("UPDATE calls SET outcome='unknown' WHERE id=?", (cid,))
                continue
            move = (later[0].c - p_fut) * (1 if bias == "BUY" else -1)
            outcome = "hit" if move >= MOVE_MIN else "miss" if move <= -MOVE_MIN else "flat"
            con.execute("UPDATE calls SET outcome=?, move=? WHERE id=?", (outcome, round(move, 2), cid))
        for tid, ts, side, entry, stop, t1, gap, lot, cost in con.execute(
                "SELECT id, ts, side, entry, stop, t1, gap, lot, cost FROM trades WHERE status='open'").fetchall():
            s = 1 if side == "BUY" else -1
            lot, cost = lot or DEMO_LOT, cost or 0.0
            stop_f, t1_f, entry_f = stop + gap, t1 + gap, entry + gap
            risk = abs(entry - stop) or 1
            be_f = entry_f + s * risk               # 1R: half comes off here and the stop moves to the entry
            r_at = lambda px_f: ((px_f - gap) - s * cost - entry) * s / risk     # R of an exit at a futures price
            status, closed, r, half, exit_f, why = None, None, None, False, None, ""
            window = [c for c in cl if ts // 900 * 900 <= c.t < ts + TRADE_EXPIRY_S]
            if cl[0].t > ts:                        # the candles no longer reach back to the entry: settle later / by hand
                continue
            for c in window:
                cur_stop = entry_f if half else stop_f
                hit_stop = c.l <= cur_stop if s > 0 else c.h >= cur_stop
                hit_t1 = c.h >= t1_f if s > 0 else c.l <= t1_f
                if hit_stop:                        # stop first if one candle touches both
                    exit_f, why = cur_stop, "breakeven after half at 1R" if half else "stop"
                    status, closed = ("won" if half else "lost"), c.t + 900
                    break
                if not half and (c.h >= be_f if s > 0 else c.l <= be_f):
                    half = True
                if hit_t1:
                    exit_f, why, status, closed = t1_f, "target" + (" after half at 1R" if half else ""), "won", c.t + 900
                    break
            if status is None and now - ts > TRADE_EXPIRY_S and window:
                exit_f, why, closed = window[-1].c, "expired (24h)" + (" after half at 1R" if half else ""), ts + TRADE_EXPIRY_S
            if exit_f is not None:
                rest = r_at(exit_f)
                r = round(0.5 * r_at(be_f) + 0.5 * rest if half else rest, 2)
                status = status if status == "lost" or r > 0 else ("lost" if r < 0 else "expired")
                if why.startswith("expired"):
                    status = "expired"
                con.execute("UPDATE trades SET status=?, closed_ts=?, result_r=?, half=?, exit_price=?, usd=?, why=? "
                            "WHERE id=?", (status, closed, r, int(half), round(exit_f - gap - s * cost, 2),
                                           round(r * risk * 100 * lot, 2), why, tid))
            elif half:
                con.execute("UPDATE trades SET half=1 WHERE id=?", (tid,))


# ---------------------------------------------------------------- demo account -> trading journal
DEMO_JOURNAL = "AuEdge Demo"


def demo_journal_id() -> int:
    """The journal account that holds the demo account's trades (created the first time it is needed)."""
    from core import journal
    found = next((a["id"] for a in journal.accounts(True) if a["name"] == DEMO_JOURNAL), None)
    if found:
        return found
    day_pct = round(100 * 350.0 / DEMO_ACCOUNT, 3)           # the demo's -$350 daily limit, as % of the account
    rules = {"phases": [{"name": "Demo test", "target_pct": None, "daily_loss_pct": day_pct, "max_loss_pct": None, "min_days": 0}],
             "funded": {"daily_loss_pct": day_pct}, "reset": "newyork"}
    return journal.create_account(DEMO_JOURNAL, "AuEdge (automatic)", DEMO_ACCOUNT, rules,
                                  "AuEdge's own demo account. Every finished demo trade is added here automatically.")


def sync_journal() -> int:
    """Write every finished demo trade into the journal once (marked with journal_id so it is never added twice)."""
    from core import journal
    with _db() as con:
        rows = con.execute("SELECT id, ts, side, entry, stop, t1, lot, cost, closed_ts, exit_price, usd, why, result_r, half "
                           "FROM trades WHERE status IN ('won','lost','expired') AND usd IS NOT NULL AND journal_id IS NULL "
                           "ORDER BY closed_ts").fetchall()
    if not rows:
        return 0
    aid = demo_journal_id()
    n = 0
    for tid, ts, side, entry, stop, t1, lot, cost, closed_ts, exit_px, usd, why, r, half in rows:
        res = journal.save_trade({"account_id": aid, "opened_at": ts, "closed_at": closed_ts, "side": side, "symbol": "XAUUSD",
                                  "lots": lot or DEMO_LOT, "entry": entry, "stop": stop, "target": t1, "exit": exit_px,
                                  "pnl": usd, "commission": 0, "setup": "AuEdge NOW call", "source": "auedge",
                                  "auedge": {"action": f"{side} NOW", "demo_trade": tid},
                                  "followed_plan": 1, "notes": f"Automatic demo trade: {why or ''}"
                                  + (" · half taken at 1R" if half else "") + f" · {r:+.2f}R · costs ${cost or 0:.2f} per side included."})
        if res.get("ok"):
            with _db() as con:
                con.execute("UPDATE trades SET journal_id=? WHERE id=?", (res["id"], tid))
            n += 1
    return n


def stats() -> dict:
    with _db() as con:
        agents = {}
        for agent, hits, misses, flats, pending in con.execute("""
                SELECT agent, SUM(outcome='hit'), SUM(outcome='miss'), SUM(outcome='flat'), SUM(outcome IS NULL)
                FROM calls GROUP BY agent""").fetchall():
            decided = (hits or 0) + (misses or 0)
            agents[agent] = {"hits": hits or 0, "misses": misses or 0, "flat": flats or 0, "pending": pending or 0,
                             "hit_rate": round(100 * hits / decided) if decided else None}
        t = dict(con.execute("SELECT status, COUNT(*) FROM trades GROUP BY status").fetchall())
        avg_r = con.execute("SELECT AVG(result_r) FROM trades WHERE status IN ('won','lost','expired')").fetchone()[0]
        recent = [dict(zip(("ts", "side", "entry", "stop", "t1", "status", "result_r"), row)) for row in con.execute(
            "SELECT ts, side, entry, stop, t1, status, result_r FROM trades ORDER BY ts DESC LIMIT 10").fetchall()]
    won, lost = t.get("won", 0), t.get("lost", 0)
    return {"agents": agents,
            "trades": {"won": won, "lost": lost, "open": t.get("open", 0), "expired": t.get("expired", 0),
                       "win_rate": round(100 * won / (won + lost)) if won + lost else None,
                       "avg_r": round(avg_r, 2) if avg_r is not None else None, "recent": recent}}


def discipline_stats(now: float | None = None, lot: float = 0.1) -> dict:
    """Today's Chief trades for the Psychology coach. The trading day starts at 18:00 New York time."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    now = now or time.time()
    ny = datetime.fromtimestamp(now, ZoneInfo("America/New_York"))
    start = ny.replace(hour=18, minute=0, second=0, microsecond=0)
    if ny.hour < 18:
        start -= timedelta(days=1)
    day0 = start.timestamp()
    with _db() as con:
        taken = con.execute("SELECT COUNT(*) FROM trades WHERE ts >= ?", (day0,)).fetchone()[0]
        today = con.execute("SELECT status, result_r, closed_ts, entry, stop FROM trades WHERE closed_ts >= ? ORDER BY closed_ts",
                            (day0,)).fetchall()
        open_n = con.execute("SELECT COUNT(*) FROM trades WHERE status='open'").fetchone()[0]
        last = [r for (r,) in con.execute("SELECT result_r FROM trades WHERE status IN ('won','lost','expired') "
                                          "ORDER BY closed_ts DESC LIMIT 10").fetchall()]
        last_loss = con.execute("SELECT MAX(closed_ts) FROM trades WHERE status IN ('lost','expired') AND result_r < 0").fetchone()[0]
    streak = 0
    for r in last:
        if r is None or r >= 0:
            break
        streak += 1
    closed = [(s, r) for s, r, *_ in today if s in ("won", "lost", "expired") and r is not None]
    usd = sum(r * abs(e - st) * 100 * lot for s, r, _, e, st in today if s in ("won", "lost", "expired") and r is not None)
    return {"trades_today": taken, "losses_today": sum(r < 0 for _, r in closed),
            "wins_today": sum(r > 0 for _, r in closed), "r_today": round(sum(r for _, r in closed), 2), "usd_today": round(usd, 2),
            "open": open_n, "losing_streak": streak, "last_loss_ts": last_loss}


def scored_calls(since: float) -> list[tuple[str, float, str]]:
    """(agent, call time, outcome) for agent calls already scored (4 hours later), for the weekly weights."""
    with _db() as con:
        return con.execute("SELECT agent, ts, outcome FROM calls WHERE ts >= ? AND outcome IN ('hit','miss','flat')",
                           (since,)).fetchall()


def demo_state(price_spot: float | None, now: float | None = None) -> dict:
    """The demo account: balance, open position with live profit/loss, closed trades (newest first) and totals."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    now = now or time.time()
    ny = datetime.fromtimestamp(now, ZoneInfo("America/New_York"))
    day0 = ny.replace(hour=18, minute=0, second=0, microsecond=0)
    if ny.hour < 18:
        day0 -= timedelta(days=1)
    week0 = (day0 - timedelta(days=(day0.weekday() + 1) % 7)).timestamp()
    day0 = day0.timestamp()
    cols = ("id", "ts", "side", "entry", "stop", "t1", "gap", "lot", "cost", "status", "closed_ts", "result_r", "half",
            "exit_price", "usd", "why")
    with _db() as con:
        rows = [dict(zip(cols, r)) for r in con.execute(f"SELECT {', '.join(cols)} FROM trades ORDER BY ts").fetchall()]
    closed, open_ = [], []
    for t in rows:
        t["lot"] = t["lot"] or DEMO_LOT
        risk = abs(t["entry"] - t["stop"]) or 1
        t["be"] = round(t["entry"] + (risk if t["side"] == "BUY" else -risk), 2)
        if t["status"] == "open":
            open_.append(t)
            continue
        if t["usd"] is None and t["result_r"] is not None:      # trades recorded before the demo account existed
            t["usd"] = round(t["result_r"] * risk * 100 * t["lot"], 2)
        if t["usd"] is not None:
            closed.append(t)
    realised = sum(t["usd"] for t in closed)
    for t in open_:
        s, oz, cost = (1 if t["side"] == "BUY" else -1), 100 * t["lot"], t["cost"] or 0
        if price_spot is None:
            t["unrealised"] = None
            continue
        rest = (price_spot - s * cost - t["entry"]) * s * oz
        t["unrealised"] = round(0.5 * (t["be"] - s * cost - t["entry"]) * s * oz + 0.5 * rest if t["half"] else rest, 2)
        t["stop_now"] = t["entry"] if t["half"] else t["stop"]
    unreal = sum(t["unrealised"] or 0 for t in open_)
    wins = [t for t in closed if t["usd"] > 0]
    eq, curve = DEMO_ACCOUNT, []
    for t in closed:
        eq += t["usd"]
        curve.append([t["closed_ts"], round(eq - DEMO_ACCOUNT, 2)])
    return {"start": DEMO_ACCOUNT, "lot": DEMO_LOT, "balance": round(DEMO_ACCOUNT + realised, 2),
            "equity": round(DEMO_ACCOUNT + realised + unreal, 2), "realised": round(realised, 2),
            "today": round(sum(t["usd"] for t in closed if (t["closed_ts"] or 0) >= day0), 2),
            "week": round(sum(t["usd"] for t in closed if (t["closed_ts"] or 0) >= week0), 2),
            "trades": len(closed), "wins": len(wins), "win_rate": round(100 * len(wins) / len(closed)) if closed else None,
            "open": open_, "closed": closed[::-1][:100], "curve": curve, "price": price_spot}
