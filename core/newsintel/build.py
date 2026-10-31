"""Builds data/news_intel.db: the event calendar with surprises, gold's reaction to each release
time, and the market context before it.

    python -m core.newsintel.build --backup <file> [--offline] [--db <path>]
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from . import store
from .calendar import build_events
from .features import features
from .minutes import load_backup_minutes
from .reactions import measure

PRICE_SOURCE = "spot_backup"


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backup", required=True, type=Path, help="pg_dump backup with the 1-minute candles")
    ap.add_argument("--offline", action="store_true", help="use cached FRED data only")
    ap.add_argument("--db", type=Path, default=store.DB, help="output database path")
    args = ap.parse_args(argv)

    m = load_backup_minutes(args.backup)
    lo, hi = int(m.t[0]), int(m.t[-1])
    events = [e for e in build_events(offline=args.offline) if lo <= e.t <= hi]

    by_time: dict[int, list] = {}
    for e in events:
        by_time.setdefault(e.t, []).append(e)
    reactions, feats, prev_t = [], [], None
    for t in sorted(by_time):
        # FOMC moves gold for longer, so its blackout after the release is 1h instead of 30 min
        blackout = 3600 if any(e.kind == "FOMC" for e in by_time[t]) else 1800
        reactions.append(measure(m, t, blackout))
        feats.append(features(m, t, prev_t))
        prev_t = t

    with store.connect(args.db) as con:
        store.replace_all(con, events, reactions, feats, PRICE_SOURCE)

    summary = {"events": len(events), "times": len(by_time),
               "incomplete": sum(r.incomplete for r in reactions),
               "by_kind": dict(Counter(e.kind for e in events))}
    print(summary)
    return summary


if __name__ == "__main__":
    main()
