"""SQLite store for the news-intelligence dataset: events, gold's reaction to each release time,
and the market context just before it. Lives in data/news_intel.db.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, astuple, fields
from pathlib import Path

from .calendar import Event
from .features import Features
from .minutes import DATA
from .reactions import Reaction

DB = DATA / "news_intel.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, kind TEXT, name TEXT, t INTEGER, actual REAL,
  previous REAL, expected REAL, sigma REAL, surprise_z REAL, components TEXT, UNIQUE (kind, t));
CREATE TABLE IF NOT EXISTS reactions (t INTEGER PRIMARY KEY, price_source TEXT, p0 REAL, r5 REAL, r15 REAL,
  r30 REAL, r60 REAL, r120 REAL, max_up REAL, max_down REAL, vol_exp REAL, cont INTEGER, settle_min INTEGER,
  atr15 REAL, move60 REAL, move120 REAL, label60 TEXT, label120 TEXT, incomplete INTEGER);
CREATE TABLE IF NOT EXISTS features (t INTEGER PRIMARY KEY, atr15 REAL, atr1h REAL, pre_range REAL,
  trend_score REAL, hours_since_prev REAL, overlap INTEGER);
"""


@contextmanager
def connect(path: Path = DB):
    """Open the database (creating tables), commit on success, and always close."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(SCHEMA)
        with con:
            yield con
    finally:
        con.close()


def _event_row(e: Event) -> tuple:
    head = next((c for c in e.components if c.headline), None)
    h = (head.actual, head.previous, head.expected, head.sigma, head.surprise_z) if head else (None,) * 5
    return (e.kind, e.name, e.t, *h, json.dumps([asdict(c) for c in e.components]))


def _names(cls) -> list[str]:
    return [f.name for f in fields(cls)]


def _insert(table: str, cols: list[str]) -> str:
    """INSERT naming every column, so the table's column order does not matter."""
    return f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"


def replace_all(con: sqlite3.Connection, events: list[Event], reactions: list[Reaction],
                feats: list[Features], price_source: str) -> None:
    """Delete and rewrite all three tables in one transaction, so a rebuild is idempotent."""
    with con:  # one transaction: a failure leaves the old data untouched
        for table in ("events", "reactions", "features"):
            con.execute(f"DELETE FROM {table}")
        con.executemany(
            "INSERT INTO events (kind, name, t, actual, previous, expected, sigma, surprise_z, components) "
            "VALUES (?,?,?,?,?,?,?,?,?)", [_event_row(e) for e in events])
        con.executemany(_insert("reactions", ["price_source", *_names(Reaction)]),
                        [(price_source, *astuple(r)) for r in reactions])
        con.executemany(_insert("features", _names(Features)), [astuple(f) for f in feats])
