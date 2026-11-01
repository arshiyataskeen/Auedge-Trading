"""Fill data/dataset.db from history: replay the saved candles with today's rules and keep every step + trade.

  - 6 months on hourly steps   -> src "backtest_1h"
  - all saved 15m history (about a month, it grows while AuEdge runs) on 15m steps -> src "backtest_15m"
Every step keeps all agents' votes, confidence and features; labels (moves after 1h / 4h / 24h, best move up /
down in 4h) are measured on the saved candles; every trade is stored with the trade reviewer's verdict.
Safe to re-run: steps and trades already stored are skipped. Then: data/exports/dataset_steps.csv / _trades.csv.

    .venv\\Scripts\\python.exe tools\\build_dataset.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import backtest  # noqa: E402
from core import dataset, trade_review  # noqa: E402


def points(name: str) -> list[dict]:
    return json.loads((ROOT / "data" / "backtest_cache" / f"{name}.json").read_text())["points"]


def snap_at(src: str, t: int) -> dict | None:
    """The stored step that decided a trade, in the trade reviewer's snapshot shape (votes, trend, confidence)."""
    import sqlite3
    con = sqlite3.connect(dataset.DB)
    row = con.execute("SELECT agents, trend, conf FROM steps WHERE src=? AND t<=? ORDER BY t DESC LIMIT 1", (src, int(t))).fetchone()
    con.close()
    if not row:
        return None
    ag = json.loads(row[0] or "{}")
    return {"ag": [[a, d.get("bias"), d.get("conf"), None] for a, d in ag.items() if d.get("status") == "OK"],
            "tr": row[1] or "", "cf": row[2]}


def main() -> None:
    run_id = time.strftime("ds_%Y%m%d_%H%M%S")
    hist = backtest.History(backtest.load_data(False, True))
    rng = backtest.data_range(hist)
    last = int(rng["last"])
    m15 = [p for p in points("fut_15m") if None not in (p.get("h"), p.get("l"), p.get("c"))]
    h1 = [p for p in points("fut_1h") if None not in (p.get("h"), p.get("l"), p.get("c"))]
    for src, step, start in (("backtest_1h", "1h", max(int(rng["first_1h"]), last - 183 * 86400)),
                             ("backtest_15m", "15m", int(rng["first_15m"]))):
        print(f"{src}: replaying from {time.strftime('%Y-%m-%d', time.gmtime(start))}")
        backtest.SETTINGS.update(record={"src": src, "run": run_id}, cache=False)
        if step == "15m":
            trades, _c, counts = asyncio.run(backtest.run(hist, 0.30, None, start, last + 1))
            steps = counts.get("_steps") or []
        else:
            trades, _c, counts, steps, _ex = asyncio.run(backtest.run_hourly(hist, 0.30, start, last + 1))
        dataset.flush()
        backtest.SETTINGS.pop("record", None)
        reviews = [trade_review.review({**t, "src": src}, snap_at(src, t["decided_t"]), m15) for t in trades]
        dataset.record_trades(src, run_id, reviews, trades)
        print(f"  {len(steps)} steps, {len(trades)} trades")
    n = dataset.label(m15) + dataset.label(h1)          # 15m candles where they exist, hourly for older steps
    print("labelled", n, "steps")
    print(json.dumps(dataset.stats(), indent=1))
    for f in dataset.export_csv():
        print("exported", f)


if __name__ == "__main__":
    main()
