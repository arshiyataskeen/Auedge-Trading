"""Training dataset: every analysis step and every trade, with full agent features and outcome labels.

data/dataset.db (SQLite), never overwritten, only added to:
  steps   one row per analysis (live every 15 min, and history replayed by tools/build_dataset.py):
          price (futures), decision, plan levels, trend, Wyckoff+Elliott side, session, killzone, and for every agent
          its vote, confidence and full metrics (JSON). Labels are filled in later from candles: price change after
          1h / 4h / 24h, and the biggest move up / down in the next 4h.
  trades  one row per finished trade (live demo + backtest) with its result and the trade reviewer's verdict.
Unique keys (src, t) and (src, entry_t, side) make re-running safe: the same step or trade is never stored twice.
Export for training: export_csv() -> data/exports/dataset_steps.csv + dataset_trades.csv (one column per feature).
"""
from __future__ import annotations

import csv
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parent.parent / "data"
DB = DATA / "dataset.db"
NY = ZoneInfo("America/New_York")
HORIZONS = {"1h": 3600, "4h": 4 * 3600, "24h": 24 * 3600}

_buf: list[tuple] = []          # backtest replays buffer their steps and write them in one go (flush)


def _db() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY, src TEXT, run TEXT, t INTEGER, price REAL, action TEXT, kind TEXT, side TEXT,
            conf REAL, score REAL, trend TEXT, htf_side TEXT, session TEXT, killzone TEXT, levels TEXT, agents TEXT,
            fwd_1h REAL, fwd_4h REAL, fwd_24h REAL, up_4h REAL, dn_4h REAL, labeled INTEGER DEFAULT 0,
            UNIQUE(src, t));
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY, src TEXT, run TEXT, entry_t INTEGER, side TEXT, entry REAL, stop REAL, t1 REAL,
            exit_t INTEGER, exit REAL, r REAL, usd REAL, why TEXT, won INTEGER, review TEXT,
            UNIQUE(src, entry_t, side));
        CREATE INDEX IF NOT EXISTS steps_t ON steps(t);""")
    return con


def session(t: float) -> str:
    h = time.gmtime(t).tm_hour
    return "Asia" if h < 7 else "London" if h < 12 else "New York" if h < 21 else "late"


def killzone(t: float) -> str | None:
    h = datetime.fromtimestamp(t, NY).hour
    return "London" if 2 <= h < 5 else "New York" if 7 <= h < 11 else None


def htf_side(results) -> str:
    """Wyckoff (Daily + 4H phase) and Elliott (Daily count) -> BUY, SELL or RANGE (same rule as the backtest)."""
    m = {r.agent: r.metrics or {} for r in results if r.status == "OK"}
    w = m.get("wyckoff", {}).get("htf_dir") or 0
    e = m.get("elliott", {}).get("macro_dir") or 0
    if (w > 0 and e >= 0) or (w == 0 and e > 0):
        return "BUY"
    if (w < 0 and e <= 0) or (w == 0 and e < 0):
        return "SELL"
    return "RANGE"


NON_VOTING = {"news_intel"}   # display-only agents: kept out of the stored steps, so the CSV export is unchanged


def _row(src: str, run: str | None, t: float, price: float, results, rep) -> tuple:
    p = rep.plan
    agents = {r.agent: {"bias": r.bias, "conf": r.confidence, "status": r.status, "label": r.bias_label,
                        "m": {k: v for k, v in (r.metrics or {}).items() if isinstance(v, (int, float, str, bool)) or v is None}}
              for r in results if r.agent not in NON_VOTING}
    return (src, run, int(t), round(price, 2), p.action, p.kind, p.side, rep.confidence, rep.weighted_score,
            (rep.today or {}).get("trend", ""), htf_side(results), session(t), killzone(t),
            json.dumps([p.entry_lo, p.entry_hi, p.stop, p.be_at, p.t1]), json.dumps(agents))


_INSERT = ("INSERT OR IGNORE INTO steps (src, run, t, price, action, kind, side, conf, score, trend, htf_side, session, "
           "killzone, levels, agents) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")


def record_step(src: str, run: str | None, t: float, price: float, results, rep, buffered: bool = False) -> None:
    """One analysis step. price = futures price (the candles the labels are measured on)."""
    row = _row(src, run, t, price, results, rep)
    if buffered:
        _buf.append(row)
        if len(_buf) >= 500:
            flush()
        return
    with _db() as con:
        con.execute(_INSERT, row)


def flush() -> None:
    if not _buf:
        return
    with _db() as con:
        con.executemany(_INSERT, _buf)
    _buf.clear()


def record_trades(src: str, run: str | None, reviews: list[dict], trades: list[dict]) -> None:
    """Finished trades (futures prices) + their reviews (core/trade_review.review), matched by entry time and side."""
    by = {(int(rv["t"]), rv["side"]): rv for rv in reviews}
    rows = [(src, run, int(t["entry_t"]), t["side"], t["entry"], t["stop"], t["t1"], int(t["exit_t"]), t.get("exit"),
             t.get("r"), t.get("usd"), t.get("why"), int((t.get("r") or 0) > 0),
             json.dumps(by.get((int(t["entry_t"]), t["side"])) or {})) for t in trades if t.get("exit_t")]
    with _db() as con:
        con.executemany("INSERT OR REPLACE INTO trades (src, run, entry_t, side, entry, stop, t1, exit_t, exit, r, usd, "
                        "why, won, review) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)


def label(candles: list[dict]) -> int:
    """Fill forward moves for steps whose 24 hours have passed, from futures 15m candles. Returns rows labelled."""
    if not candles:
        return 0
    ts = [c["t"] for c in candles]
    last = ts[-1]
    from bisect import bisect_left
    done = 0
    with _db() as con:
        rows = con.execute("SELECT id, t, price FROM steps WHERE labeled = 0 AND t + ? <= ? AND t >= ?",
                           (HORIZONS["24h"], last, ts[0])).fetchall()
        out = []
        for sid, t, price in rows:
            def close_at(h):
                i = bisect_left(ts, t + h) - 1          # the candle that was open at t + h
                return candles[i]["c"] if 0 <= i < len(candles) else None
            win = candles[bisect_left(ts, t):bisect_left(ts, t + HORIZONS["4h"])]
            f = {k: close_at(h) for k, h in HORIZONS.items()}
            if None in f.values() or not win:
                continue
            out.append((round(f["1h"] - price, 2), round(f["4h"] - price, 2), round(f["24h"] - price, 2),
                        round(max(c["h"] for c in win) - price, 2), round(price - min(c["l"] for c in win), 2), sid))
        con.executemany("UPDATE steps SET fwd_1h=?, fwd_4h=?, fwd_24h=?, up_4h=?, dn_4h=?, labeled=1 WHERE id=?", out)
        done = len(out)
    return done


def stats() -> dict:
    with _db() as con:
        s = con.execute("SELECT src, COUNT(*), SUM(labeled), MIN(t), MAX(t) FROM steps GROUP BY src").fetchall()
        tr = con.execute("SELECT src, COUNT(*), SUM(won) FROM trades GROUP BY src").fetchall()
    return {"steps": [dict(zip(("src", "n", "labeled", "first", "last"), r)) for r in s],
            "trades": [dict(zip(("src", "n", "won"), r)) for r in tr]}


def export_csv() -> list[Path]:
    """Flat CSVs for training: one column per agent feature (agent__vote, agent__conf, agent__<metric>)."""
    out = DATA / "exports"
    out.mkdir(exist_ok=True)
    with _db() as con:
        con.row_factory = sqlite3.Row
        steps = [dict(r) for r in con.execute("SELECT * FROM steps ORDER BY t")]
        trades = [dict(r) for r in con.execute("SELECT * FROM trades ORDER BY entry_t")]
    flat, cols = [], []
    for s in steps:
        ag = json.loads(s.pop("agents") or "{}")
        lv = json.loads(s.pop("levels") or "[]")
        s.update({k: v for k, v in zip(("entry_lo", "entry_hi", "stop", "half_1r", "target"), lv)})
        for a, d in ag.items():
            s[f"{a}__vote"], s[f"{a}__conf"] = d.get("bias"), d.get("conf")
            for k, v in (d.get("m") or {}).items():
                s[f"{a}__{k}"] = v
        flat.append(s)
        cols += [k for k in s if k not in cols]
    files = []
    for name, rows, fields in (("dataset_steps.csv", flat, cols),
                               ("dataset_trades.csv", trades, list(trades[0]) if trades else [])):
        f = out / name
        with f.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        files.append(f)
    return files
