"""Daily safety copy and readable exports of everything AuEdge records.

Backup (once a day, last 30 kept): D:\\study material\\AuEdge-backups\\auedge_YYYY-MM-DD.zip with
  track.db (every analysis, agent call, demo trade), journal.db + screenshots, agent votes and the review log,
  the candle history and the newest backtest / health-check / review results.
  Databases are copied with SQLite's own backup, so a copy taken while AuEdge is writing is still consistent.

Exports (refreshed daily, plain CSV, easy to open in Excel or to review later): data\\exports\\
  journal_trades.csv   every journal trade (all accounts, incl. "AuEdge Demo")
  demo_trades.csv      every AuEdge demo trade (open and closed)
  daily_results.csv    demo result per trading day
  calls_daily.csv      per day and agent: calls, right / wrong (4 hours later)
  README.txt           what each file holds
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
# Next to the AuEdge folder on a PC; on Railway the start script points this into the permanent volume (data/backups).
BACKUPS = Path(os.getenv("AUEDGE_BACKUP_DIR") or ROOT.parent / "AuEdge-backups")
EXPORTS = DATA / "exports"
KEEP = 30
NY = ZoneInfo("America/New_York")


def _trading_day(ts: float) -> str:
    return (datetime.fromtimestamp(ts, NY) + timedelta(hours=6)).strftime("%Y-%m-%d")


def _iso(ts) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""


def _copy_db(src: Path, dst: Path) -> None:
    s, d = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        s.close()
        d.close()


def backup() -> Path | None:
    """Zip today's copy (skipped if today's zip already exists). Returns the zip path."""
    BACKUPS.mkdir(parents=True, exist_ok=True)
    zpath = BACKUPS / f"auedge_{datetime.now():%Y-%m-%d}.zip"
    if zpath.exists():
        return zpath
    tmp = BACKUPS / "_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        for name in ("track.db", "journal.db"):
            if (DATA / name).exists():
                _copy_db(DATA / name, tmp / name)
        with zipfile.ZipFile(zpath.with_suffix(".part"), "w", zipfile.ZIP_DEFLATED) as z:
            for f in tmp.iterdir():
                z.write(f, f"data/{f.name}")
            for name in ("agent_votes.json", "review_log.json", "demo_month.txt", "news_events.json", "cot_gold.json"):
                if (DATA / name).exists():
                    z.write(DATA / name, f"data/{name}")
            for f in (DATA / "journal_files").glob("*") if (DATA / "journal_files").exists() else []:
                z.write(f, f"data/journal_files/{f.name}")
            for f in (DATA / "backtest_cache").glob("*.json"):
                z.write(f, f"data/backtest_cache/{f.name}")
            bt = DATA / "backtests"
            for prefix in ("bt_", "hc_", "rv_"):          # newest 5 of each kind
                for f in sorted(bt.glob(f"{prefix}*.json"), reverse=True)[:5]:
                    z.write(f, f"data/backtests/{f.name}")
            for f in EXPORTS.glob("*") if EXPORTS.exists() else []:
                z.write(f, f"data/exports/{f.name}")
        zpath.with_suffix(".part").replace(zpath)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for old in sorted(BACKUPS.glob("auedge_*.zip"))[:-KEEP]:
        old.unlink()
    return zpath


def _write_csv(path: Path, header: list[str], rows) -> int:
    tmp = path.with_suffix(".tmp")
    n = 0
    with tmp.open("w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig: opens cleanly in Excel
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)
            n += 1
    tmp.replace(path)
    return n


def export() -> dict:
    """Refresh the CSV files in data/exports."""
    EXPORTS.mkdir(parents=True, exist_ok=True)
    out = {}
    # journal (all accounts)
    if (DATA / "journal.db").exists():
        con = sqlite3.connect(DATA / "journal.db")
        try:
            rows = con.execute("""SELECT a.name, p.name, t.opened_at, t.closed_at, t.symbol, t.side, t.lots, t.entry, t.stop, t.target,
                                         t.exit, t.pnl, t.commission, t.setup, t.source, t.emotion, t.followed_plan, t.rating,
                                         t.mistakes, t.notes
                                  FROM trades t JOIN accounts a ON a.id = t.account_id LEFT JOIN phases p ON p.id = t.phase_id
                                  ORDER BY t.opened_at""").fetchall()
        finally:
            con.close()
        out["journal_trades.csv"] = _write_csv(EXPORTS / "journal_trades.csv",
            ["account", "phase", "opened", "closed", "symbol", "side", "lots", "entry", "stop", "target", "exit", "pnl",
             "commission", "net", "setup", "source", "mood", "followed_plan", "rating", "mistakes", "notes"],
            ([a, ph, _iso(o), _iso(c), sym, sd, lots, e, st, tg, ex, pnl, com,
              round((pnl or 0) - (com or 0), 2) if pnl is not None else "", setup, src, emo,
              "" if fp is None else ("yes" if fp else "no"), rat, mis, notes]
             for a, ph, o, c, sym, sd, lots, e, st, tg, ex, pnl, com, setup, src, emo, fp, rat, mis, notes in rows))
    # AuEdge demo trades + per-day results + agent calls per day
    if (DATA / "track.db").exists():
        con = sqlite3.connect(DATA / "track.db")
        try:
            trades = con.execute("SELECT ts, side, entry, stop, t1, lot, status, closed_ts, exit_price, result_r, usd, why "
                                 "FROM trades ORDER BY ts").fetchall()
            calls = con.execute("SELECT ts, agent, bias, outcome FROM calls ORDER BY ts").fetchall()
        finally:
            con.close()
        out["demo_trades.csv"] = _write_csv(EXPORTS / "demo_trades.csv",
            ["opened", "trading_day", "side", "entry", "stop", "target", "lot", "status", "closed", "exit", "result_R", "usd", "why"],
            ([_iso(ts), _trading_day(ts), sd, e, st, t1, lot, status, _iso(cts), ex, r, usd, why]
             for ts, sd, e, st, t1, lot, status, cts, ex, r, usd, why in trades))
        days: dict[str, list] = {}
        for ts, sd, e, st, t1, lot, status, cts, ex, r, usd, why in trades:
            if usd is not None and cts:
                d = days.setdefault(_trading_day(cts), [0, 0, 0, 0.0])
                d[0] += 1
                d[1] += usd > 0
                d[2] += usd < 0
                d[3] += usd
        bal, rows = 25000.0, []
        for k in sorted(days):
            n, w, l, pnl = days[k]
            bal += pnl
            rows.append([k, n, w, l, round(pnl, 2), round(bal, 2)])
        out["daily_results.csv"] = _write_csv(EXPORTS / "daily_results.csv",
                                              ["trading_day", "trades", "won", "lost", "usd", "balance"], rows)
        agg: dict[tuple, list] = {}
        for ts, agent, bias, outcome in calls:
            a = agg.setdefault((_trading_day(ts), agent), [0, 0, 0, 0])
            a[0] += 1
            a[1] += outcome == "hit"
            a[2] += outcome == "miss"
            a[3] += outcome == "flat"
        out["calls_daily.csv"] = _write_csv(EXPORTS / "calls_daily.csv", ["trading_day", "agent", "calls", "right", "wrong", "flat"],
                                            ([d, a, *v] for (d, a), v in sorted(agg.items())))
    (EXPORTS / "README.txt").write_text(
        "AuEdge exports, refreshed once a day (also when AuEdge starts).\n\n"
        "journal_trades.csv  every trade in the trading journal (all accounts, including 'AuEdge Demo').\n"
        "demo_trades.csv     every AuEdge demo-account trade (0.1 lot), open and closed.\n"
        "daily_results.csv   the demo account's result per trading day (18:00-17:00 New York) and running balance.\n"
        "calls_daily.csv     each agent's calls per trading day and how many were right / wrong 4 hours later.\n\n"
        "Full copies of everything (databases, settings, history) are zipped daily in the AuEdge-backups folder next to AuEdge.\n",
        encoding="utf-8")
    _write_state({"last_export": time.time(), "files": out})
    return out


def _write_state(d: dict) -> None:
    p = DATA / "backup_state.json"
    try:
        old = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        old = {}
    p.write_text(json.dumps({**old, **d}, indent=1), encoding="utf-8")


def daily() -> dict:
    """Exports first (so the zip holds them), then the backup."""
    files = export()
    z = backup()
    _write_state({"last_backup": time.time(), "backup_file": str(z) if z else None})
    return {"exports": files, "backup": str(z) if z else None}
