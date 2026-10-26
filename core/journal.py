"""Trading journal for prop-firm accounts: your own rules per phase (Phase 1, Phase 2, ... then Funded), every trade
you take (typed in, or copied from an AuEdge call), and the rule check for each phase.

Stored in data/journal.db (separate from AuEdge's own track record). Screenshots go to data/journal_files/.
Rule check (closed trades only; your broker's floating P&L is not known here):
- target: profit since the phase started >= target % of the account size, plus the minimum trading days
- daily loss: a day's closed loss reaches daily % of the account size (or of that day's starting balance)
- max loss: balance falls to size x max % below the phase start (static) or below the highest balance (trailing)
"""
from __future__ import annotations

import base64
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parent.parent / "data"
DB = DATA / "journal.db"
FILES = DATA / "journal_files"
OZ_PER_LOT = 100                     # XAUUSD: 1 lot = 100 oz, so 0.1 lot = $10 per $1 move
RESETS = {"utc": ("UTC", 0), "prague": ("Europe/Prague", 0), "newyork": ("America/New_York", 17), "india": ("Asia/Kolkata", 0)}
TRADE_FIELDS = ("account_id", "phase_id", "opened_at", "closed_at", "side", "symbol", "lots", "entry", "stop", "target",
                "exit", "pnl", "commission", "setup", "source", "auedge", "emotion", "followed_plan", "mistakes", "notes",
                "rating", "image")


@contextmanager
def _db():
    """Open journal.db, commit on success, and always close (an open handle can lock the file on Windows)."""
    con = _connect()
    try:
        with con:
            yield con
    finally:
        con.close()


def _connect() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript("""
      CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, name TEXT, firm TEXT, size REAL, created_at REAL,
        rules TEXT, notes TEXT, archived INTEGER DEFAULT 0);
      CREATE TABLE IF NOT EXISTS phases (id INTEGER PRIMARY KEY, account_id INTEGER, idx INTEGER, name TEXT,
        start_balance REAL, started_at REAL, ended_at REAL, result TEXT, note TEXT);
      CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, account_id INTEGER, phase_id INTEGER, opened_at REAL,
        closed_at REAL, side TEXT, symbol TEXT, lots REAL, entry REAL, stop REAL, target REAL, exit REAL, pnl REAL,
        commission REAL, setup TEXT, source TEXT, auedge TEXT, emotion TEXT, followed_plan INTEGER, mistakes TEXT,
        notes TEXT, rating INTEGER, image TEXT, created_at REAL);
    """)
    return con


# ---------------------------------------------------------------- rules
def clean_rules(r: dict) -> dict:
    """Validate the account's rules (from the New account form)."""
    def num(v, lo, hi, default=None):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return default
        return v if lo <= v <= hi else default

    phases = []
    for p in (r.get("phases") or [])[:5]:
        phases.append({"name": str(p.get("name") or f"Phase {len(phases) + 1}")[:30],
                       "target_pct": num(p.get("target_pct"), 0.1, 100),
                       "daily_loss_pct": num(p.get("daily_loss_pct"), 0.1, 100),
                       "max_loss_pct": num(p.get("max_loss_pct"), 0.1, 100),
                       "max_loss_type": "trailing" if p.get("max_loss_type") == "trailing" else "static",
                       "min_days": int(num(p.get("min_days"), 0, 365, 0) or 0),
                       "consistency_pct": num(p.get("consistency_pct"), 1, 100)})
    f = r.get("funded") or {}
    funded = {"name": "Funded", "target_pct": None, "daily_loss_pct": num(f.get("daily_loss_pct"), 0.1, 100),
              "max_loss_pct": num(f.get("max_loss_pct"), 0.1, 100),
              "max_loss_type": "trailing" if f.get("max_loss_type") == "trailing" else "static", "min_days": 0,
              "profit_split": num(f.get("profit_split"), 0, 100), "consistency_pct": num(f.get("consistency_pct"), 1, 100)}
    return {"phases": phases, "funded": funded, "reset": r.get("reset") if r.get("reset") in RESETS else "utc",
            "daily_base": "day_start" if r.get("daily_base") == "day_start" else "initial"}


def phase_rules(rules: dict, idx: int) -> dict:
    return rules["phases"][idx] if idx < len(rules["phases"]) else rules["funded"]


def day_key(ts: float, reset: str) -> str:
    tz, hour = RESETS.get(reset, RESETS["utc"])
    d = datetime.fromtimestamp(ts - hour * 3600, ZoneInfo(tz))          # a 17:00 reset counts 17:00-17:00 as one day
    return d.strftime("%Y-%m-%d")


def net(t: dict) -> float | None:
    if t["pnl"] is None:
        return None
    return round(t["pnl"] - (t["commission"] or 0), 2)


def planned_rr(t: dict) -> float | None:
    """Reward:risk of the plan when the trade was opened: target distance / stop distance."""
    if not t["entry"] or not t["stop"] or not t["target"] or t["entry"] == t["stop"]:
        return None
    return round(abs(t["target"] - t["entry"]) / abs(t["entry"] - t["stop"]), 2)


def r_multiple(t: dict) -> float | None:
    n = net(t)
    if n is None or not t["entry"] or not t["stop"] or not t["lots"]:
        return None
    risk = abs(t["entry"] - t["stop"]) * t["lots"] * OZ_PER_LOT
    return round(n / risk, 2) if risk else None


def check_phase(acc: dict, ph: dict, trades: list[dict], now: float | None = None) -> dict:
    """Progress and rule status of one phase from its closed trades."""
    now = now or time.time()
    rules, size = acc["rules"], acc["size"]
    pr = phase_rules(rules, ph["idx"])
    closed = sorted([t for t in trades if net(t) is not None], key=lambda t: t["closed_at"] or t["opened_at"] or 0)
    bal = peak = ph["start_balance"]
    days: dict[str, float] = {}
    day_start: dict[str, float] = {}
    breach = None
    max_amt = size * pr["max_loss_pct"] / 100 if pr.get("max_loss_pct") else None
    daily_amt = size * pr["daily_loss_pct"] / 100 if pr.get("daily_loss_pct") else None
    for t in closed:
        k = day_key(t["closed_at"] or t["opened_at"], rules["reset"])
        day_start.setdefault(k, bal)
        bal += net(t)
        days[k] = days.get(k, 0.0) + net(t)
        floor = (peak if pr.get("max_loss_type") == "trailing" else ph["start_balance"]) - max_amt if max_amt else None
        peak = max(peak, bal)
        lim = (day_start[k] * pr["daily_loss_pct"] / 100 if rules["daily_base"] == "day_start" else daily_amt) if daily_amt else None
        if not breach and lim and days[k] <= -lim:
            breach = {"rule": "daily", "day": k, "text": f"Daily loss limit hit on {k}: {days[k]:+,.2f} (limit -{lim:,.2f})"}
        if not breach and floor is not None and bal <= floor:
            breach = {"rule": "max", "day": k, "text": f"Max loss limit hit on {k} (balance {bal:,.2f}, limit {floor:,.2f})"}
    profit = bal - ph["start_balance"]
    target_amt = size * pr["target_pct"] / 100 if pr.get("target_pct") else None
    today = day_key(now, rules["reset"])
    today_pnl = days.get(today, 0.0)
    today_lim = ((day_start.get(today, bal) * pr["daily_loss_pct"] / 100) if rules["daily_base"] == "day_start"
                 else daily_amt) if daily_amt else None
    floor_now = ((peak if pr.get("max_loss_type") == "trailing" else ph["start_balance"]) - max_amt) if max_amt else None
    n_days = len(days)
    # Consistency: how much of the profit came from the single best day (many firms cap it, e.g. 30-50%)
    best_day = max(days.items(), key=lambda kv: kv[1]) if days else None
    share = round(100 * best_day[1] / profit, 1) if best_day and profit > 0 and best_day[1] > 0 else None
    cons_lim = pr.get("consistency_pct")
    cons_bad = bool(cons_lim and share is not None and share > cons_lim)
    # profit needed so the best day falls back within the limit (if no bigger day comes)
    cons_need = round(best_day[1] * 100 / cons_lim - profit, 2) if cons_bad else None
    if ph["result"]:
        status = ph["result"]
    elif breach:
        status = "breached"
    elif target_amt is not None and profit >= target_amt and n_days >= pr["min_days"] and not cons_bad:
        status = "target_reached"
    elif target_amt is not None and profit >= target_amt and cons_bad:
        status = "need_consistency"
    elif target_amt is not None and profit >= target_amt:
        status = "need_days"
    else:
        status = "active"
    wins = [net(t) for t in closed if net(t) > 0]
    losses = [net(t) for t in closed if net(t) < 0]
    rs = [r_multiple(t) for t in closed if r_multiple(t) is not None]
    prr = [planned_rr(t) for t in closed if planned_rr(t) is not None]
    win_rate = len(wins) / len(closed) if closed else None
    avg_prr = sum(prr) / len(prr) if prr else None
    buckets = [("−1R or worse", None, -1), ("−1R to 0", -1, 0), ("0 to 1R", 0, 1), ("1R to 2R", 1, 2), ("2R to 3R", 2, 3), ("3R+", 3, None)]
    dist = [{"label": lb, "n": sum(1 for r in rs if (lo is None or r > lo) and (hi is None or r <= hi))} for lb, lo, hi in buckets]
    lots = [t["lots"] for t in closed if t["lots"]]
    win_days = [v for v in days.values() if v > 0]
    loss_days = [v for v in days.values() if v < 0]
    fp = [t for t in closed if t["followed_plan"] is not None]
    setups: dict[str, list[float]] = {}
    for t in closed:
        setups.setdefault((t["setup"] or "No setup").strip() or "No setup", []).append(net(t))
    emotions: dict[str, list[float]] = {}
    for t in closed:
        if t["emotion"]:
            emotions.setdefault(t["emotion"], []).append(net(t))
    return {
        "rules": pr, "status": status, "breach": breach, "balance": round(bal, 2), "profit": round(profit, 2),
        "target_amt": round(target_amt, 2) if target_amt is not None else None,
        "target_left": round(max(0.0, target_amt - profit), 2) if target_amt is not None else None,
        "days_traded": n_days, "min_days": pr["min_days"],
        "daily_limit": round(today_lim, 2) if today_lim else None, "today_pnl": round(today_pnl, 2),
        "daily_room": round(today_lim + min(0.0, today_pnl), 2) if today_lim else None,
        "max_floor": round(floor_now, 2) if floor_now is not None else None,
        "max_room": round(bal - floor_now, 2) if floor_now is not None else None,
        "equity": [[t["closed_at"] or t["opened_at"], round(sum(net(x) for x in closed[:i + 1]), 2)] for i, t in enumerate(closed)],
        "days": [{"day": k, "pnl": round(v, 2), "n": sum(1 for t in closed if day_key(t["closed_at"] or t["opened_at"], rules["reset"]) == k)}
                 for k, v in sorted(days.items())],
        "rr": {"n_with_stop": len(rs), "n_without_stop": len(closed) - len(rs), "avg_planned": round(avg_prr, 2) if avg_prr else None,
               "avg_achieved": round(sum(rs) / len(rs), 2) if rs else None,
               "avg_win_r": round(sum(r for r in rs if r > 0) / len([r for r in rs if r > 0]), 2) if any(r > 0 for r in rs) else None,
               "avg_loss_r": round(sum(r for r in rs if r < 0) / len([r for r in rs if r < 0]), 2) if any(r < 0 for r in rs) else None,
               "breakeven_win_rate": round(100 / (1 + avg_prr)) if avg_prr else None,
               "win_rate": round(100 * win_rate) if win_rate is not None else None,
               "expectancy_usd": round(sum(net(t) for t in closed) / len(closed), 2) if closed else None,
               "expectancy_r": round(sum(rs) / len(rs), 2) if rs else None,
               "hit_target": sum(1 for t in closed if t["target"] and t["exit"] is not None and
                                 (t["exit"] - t["target"]) * (1 if t["side"] == "BUY" else -1) >= -0.01),
               "with_target": sum(1 for t in closed if t["target"] and t["exit"] is not None),
               "dist": dist},
        "consistency": {"limit_pct": cons_lim, "best_day": {"day": best_day[0], "pnl": round(best_day[1], 2)} if best_day else None,
                        "best_day_share": share, "ok": (not cons_bad) if cons_lim else None, "profit_needed": cons_need,
                        "win_days": len(win_days), "loss_days": len(loss_days),
                        "avg_win_day": round(sum(win_days) / len(win_days), 2) if win_days else None,
                        "avg_loss_day": round(sum(loss_days) / len(loss_days), 2) if loss_days else None,
                        "worst_day": round(min(days.values()), 2) if days else None,
                        "biggest_trade_share": round(100 * max(wins) / profit, 1) if wins and profit > 0 else None,
                        "avg_lots": round(sum(lots) / len(lots), 2) if lots else None, "max_lots": max(lots) if lots else None,
                        "min_lots": min(lots) if lots else None,
                        "lot_spread": round(max(lots) / (sum(lots) / len(lots)), 2) if lots else None},
        "stats": {"n": len(closed), "open": len([t for t in trades if net(t) is None]), "wins": len(wins), "losses": len(losses),
                  "win_rate": round(100 * len(wins) / len(closed)) if closed else None,
                  "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
                  "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
                  "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and wins else None,
                  "best": max((net(t) for t in closed), default=None), "worst": min((net(t) for t in closed), default=None),
                  "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
                  "followed_plan_pct": round(100 * sum(t["followed_plan"] for t in fp) / len(fp)) if fp else None,
                  "followed_pnl": round(sum(net(t) for t in fp if t["followed_plan"]), 2) if fp else None,
                  "broke_pnl": round(sum(net(t) for t in fp if not t["followed_plan"]), 2) if fp else None,
                  "by_setup": sorted([{"setup": k, "n": len(v), "pnl": round(sum(v), 2),
                                       "win_rate": round(100 * sum(x > 0 for x in v) / len(v))} for k, v in setups.items()],
                                     key=lambda x: -x["pnl"]),
                  "by_emotion": sorted([{"emotion": k, "n": len(v), "pnl": round(sum(v), 2)} for k, v in emotions.items()],
                                       key=lambda x: -x["pnl"])},
    }


# ---------------------------------------------------------------- accounts
def _account_row(con, aid: int) -> dict | None:
    r = con.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
    if not r:
        return None
    a = dict(r)
    a["rules"] = json.loads(a["rules"])
    return a


def _trade(r) -> dict:
    t = dict(r)
    t["auedge"] = json.loads(t["auedge"]) if t["auedge"] else None
    t["net"], t["r"], t["planned_rr"] = net(t), r_multiple(t), planned_rr(t)
    return t


def account(aid: int, with_trades: bool = True) -> dict | None:
    with _db() as con:
        a = _account_row(con, aid)
        if not a:
            return None
        phases = [dict(p) for p in con.execute("SELECT * FROM phases WHERE account_id=? ORDER BY idx", (aid,))]
        trades = [_trade(t) for t in con.execute("SELECT * FROM trades WHERE account_id=? ORDER BY opened_at DESC, id DESC", (aid,))]
    for t in trades:                       # the firm's trading day of each trade (for the calendar)
        t["day"] = day_key(t["closed_at"] or t["opened_at"], a["rules"]["reset"])
    for p in phases:
        pt = [t for t in trades if t["phase_id"] == p["id"]]
        p["check"] = check_phase(a, p, pt)
        p["is_funded"] = p["idx"] >= len(a["rules"]["phases"])
    a["phases"] = phases
    a["current"] = next((p for p in phases if not p["result"]), phases[-1] if phases else None)
    a["total_phases"] = len(a["rules"]["phases"])
    if with_trades:
        a["trades"] = trades
    return a


def accounts(include_archived: bool = False) -> list[dict]:
    with _db() as con:
        ids = [r[0] for r in con.execute("SELECT id FROM accounts WHERE archived=0 OR ? ORDER BY created_at DESC",
                                         (int(include_archived),))]
    out = []
    for aid in ids:
        a = account(aid)
        last = a["trades"][0] if a["trades"] else None
        a["n_trades"], a["last_trade_at"] = len(a.pop("trades")), (last["opened_at"] if last else None)
        out.append(a)
    return out


def create_account(name: str, firm: str, size: float, rules: dict, notes: str = "") -> int:
    rules = clean_rules(rules)
    with _db() as con:
        cur = con.execute("INSERT INTO accounts (name, firm, size, created_at, rules, notes) VALUES (?,?,?,?,?,?)",
                          (name[:60], firm[:60], size, time.time(), json.dumps(rules), notes[:2000]))
        aid = cur.lastrowid
        con.execute("INSERT INTO phases (account_id, idx, name, start_balance, started_at) VALUES (?,?,?,?,?)",
                    (aid, 0, phase_rules(rules, 0)["name"], size, time.time()))
    return aid


def update_account(aid: int, name: str, firm: str, notes: str, rules: dict | None) -> None:
    with _db() as con:
        con.execute("UPDATE accounts SET name=?, firm=?, notes=? WHERE id=?", (name[:60], firm[:60], notes[:2000], aid))
        if rules is not None:
            con.execute("UPDATE accounts SET rules=? WHERE id=?", (json.dumps(clean_rules(rules)), aid))


def archive_account(aid: int, archived: bool) -> None:
    with _db() as con:
        con.execute("UPDATE accounts SET archived=? WHERE id=?", (int(archived), aid))


def advance(aid: int, result: str, note: str = "", next_balance: float | None = None) -> dict:
    """Close the current phase as passed or failed. Passed: the next phase (or Funded) starts."""
    a = account(aid, with_trades=False)
    cur = a["current"] if a else None
    if not cur or cur["result"]:
        return {"ok": False, "error": "No active phase."}
    if result not in ("passed", "failed"):
        return {"ok": False, "error": "Choose passed or failed."}
    if result == "passed" and cur["is_funded"]:
        return {"ok": False, "error": "The funded phase has no target to pass. Mark it failed or archive the account."}
    with _db() as con:
        con.execute("UPDATE phases SET result=?, ended_at=?, note=? WHERE id=?", (result, time.time(), note[:500], cur["id"]))
        if result == "passed":
            idx = cur["idx"] + 1
            con.execute("INSERT INTO phases (account_id, idx, name, start_balance, started_at) VALUES (?,?,?,?,?)",
                        (aid, idx, phase_rules(a["rules"], idx)["name"], next_balance or a["size"], time.time()))
    return {"ok": True}


def reopen_phase(aid: int) -> dict:
    """Undo the last 'passed' / 'failed' mark (the phase it opened is removed if it has no trades)."""
    with _db() as con:
        ph = [dict(p) for p in con.execute("SELECT * FROM phases WHERE account_id=? ORDER BY idx", (aid,))]
        if not ph:
            return {"ok": False, "error": "No phases."}
        last = ph[-1]
        if not last["result"] and len(ph) > 1:
            if con.execute("SELECT COUNT(*) FROM trades WHERE phase_id=?", (last["id"],)).fetchone()[0]:
                return {"ok": False, "error": "The new phase already has trades. Move or delete them first."}
            con.execute("DELETE FROM phases WHERE id=?", (last["id"],))
            last = ph[-2]
        if not last["result"]:
            return {"ok": False, "error": "Nothing to undo."}
        con.execute("UPDATE phases SET result=NULL, ended_at=NULL, note=NULL WHERE id=?", (last["id"],))
    return {"ok": True}


# ---------------------------------------------------------------- trades
def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def save_trade(data: dict, tid: int | None = None) -> dict:
    a = account(int(data.get("account_id") or 0), with_trades=False)
    if not a:
        return {"ok": False, "error": "Pick an account."}
    phase_id = int(data.get("phase_id") or 0) or a["current"]["id"]
    if phase_id not in {p["id"] for p in a["phases"]}:
        return {"ok": False, "error": "That phase belongs to another account."}
    side = "SELL" if str(data.get("side", "")).upper() == "SELL" else "BUY"
    t = {"account_id": a["id"], "phase_id": phase_id, "opened_at": _num(data.get("opened_at")) or time.time(),
         "closed_at": _num(data.get("closed_at")), "side": side, "symbol": (data.get("symbol") or "XAUUSD")[:20],
         "lots": _num(data.get("lots")), "entry": _num(data.get("entry")), "stop": _num(data.get("stop")),
         "target": _num(data.get("target")), "exit": _num(data.get("exit")), "pnl": _num(data.get("pnl")),
         "commission": _num(data.get("commission")) or 0.0, "setup": (data.get("setup") or "")[:60],
         "source": "auedge" if data.get("source") == "auedge" else "manual",
         "auedge": json.dumps(data["auedge"])[:4000] if data.get("auedge") else None,
         "emotion": (data.get("emotion") or "")[:30] or None,
         "followed_plan": None if data.get("followed_plan") in (None, "") else int(bool(data.get("followed_plan"))),
         "mistakes": (data.get("mistakes") or "")[:1000], "notes": (data.get("notes") or "")[:4000],
         "rating": int(_num(data.get("rating")) or 0) or None, "image": None}
    # P&L: typed in (your broker's real number, best), otherwise worked out from entry / exit / lots (XAUUSD)
    if t["pnl"] is None and t["exit"] is not None and t["entry"] is not None and t["lots"]:
        t["pnl"] = round((t["exit"] - t["entry"]) * (1 if side == "BUY" else -1) * t["lots"] * OZ_PER_LOT, 2)
    if t["pnl"] is not None and not t["closed_at"]:
        t["closed_at"] = t["opened_at"]
    with _db() as con:
        old = con.execute("SELECT image FROM trades WHERE id=?", (tid,)).fetchone() if tid else None
        t["image"] = old["image"] if old else None
        img = data.get("image_data")
        if img == "remove":
            t["image"] = None
        elif img:
            m = re.match(r"data:image/(png|jpeg|webp);base64,(.+)", img, re.S)
            raw = base64.b64decode(m.group(2)) if m else b""
            if not m or len(raw) > 6 * 1024 * 1024:
                return {"ok": False, "error": "Screenshot must be a PNG, JPG or WEBP under 6 MB."}
            FILES.mkdir(exist_ok=True)
            name = f"t{int(time.time() * 1000)}.{'jpg' if m.group(1) == 'jpeg' else m.group(1)}"
            (FILES / name).write_bytes(raw)
            t["image"] = name
        if tid:
            con.execute(f"UPDATE trades SET {', '.join(k + '=?' for k in TRADE_FIELDS)} WHERE id=?",
                        [t[k] for k in TRADE_FIELDS] + [tid])
        else:
            cur = con.execute(f"INSERT INTO trades ({', '.join(TRADE_FIELDS)}, created_at) VALUES ({', '.join('?' * len(TRADE_FIELDS))}, ?)",
                              [t[k] for k in TRADE_FIELDS] + [time.time()])
            tid = cur.lastrowid
    return {"ok": True, "id": tid}


def all_trades(include_archived: bool = True) -> list[dict]:
    """Every trade with its account and phase name (the All records page)."""
    with _db() as con:
        rows = con.execute("""SELECT t.*, a.name AS account, a.size AS account_size, a.archived AS archived, p.name AS phase,
                                     p.idx AS phase_idx, a.rules AS rules
                              FROM trades t JOIN accounts a ON a.id = t.account_id LEFT JOIN phases p ON p.id = t.phase_id
                              WHERE a.archived = 0 OR ? ORDER BY t.opened_at DESC, t.id DESC""", (int(include_archived),)).fetchall()
    out = []
    for r in rows:
        t = _trade(r)
        rules = json.loads(t.pop("rules"))
        n_phases = len(rules["phases"])
        t["day"] = day_key(t["closed_at"] or t["opened_at"], rules.get("reset", "utc"))
        t["phase"] = "Funded" if (t["phase_idx"] or 0) >= n_phases else t["phase"]
        t["planned_rr"] = planned_rr(t)
        out.append(t)
    return out


def delete_trade(tid: int) -> None:
    with _db() as con:
        con.execute("DELETE FROM trades WHERE id=?", (tid,))


def image_path(name: str) -> Path | None:
    if not re.fullmatch(r"t\d+\.(png|jpg|webp)", name):
        return None
    f = FILES / name
    return f if f.exists() else None
