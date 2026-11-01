"""CLI: python -m core.newsintel.ml [--label label60|label120] — runs the walk-forward, writes the report, prints the verdict."""
from __future__ import annotations

import argparse
from datetime import datetime

from . import export, harness, report
from .data import load
from ..minutes import DATA

REPORT_PATHS = {"label60": DATA / "news_intel_report.html", "label120": DATA / "news_intel_report_120.html"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m core.newsintel.ml", description=__doc__)
    ap.add_argument("--label", choices=harness.LABELS, default="label60")
    ap.add_argument("--export", action="store_true", help="fit on all history and save the live-app artifacts")
    ap.add_argument("--until", metavar="YYYY-MM-DD", help="with --export: use only rows before this date")
    ap.add_argument("--out", metavar="DIR", help="with --export: write here instead of the live models folder")
    args = ap.parse_args(argv)
    if args.until and not args.export:
        ap.error("--until only works with --export")
    if args.until:
        try:
            datetime.strptime(args.until, "%Y-%m-%d")
        except ValueError:
            ap.error(f"--until must be YYYY-MM-DD, got {args.until!r}")
    if args.export:
        meta = export.export(load(), out=args.out or export.MODELS_DIR, until=args.until)
        print(f"Exported news models (trained through {meta['trained_through']}, primary {meta['primary_name']}, "
              f"go-live {'yes' if meta['go_live'] else 'no'}) to {args.out or export.MODELS_DIR}")
        return 0
    res = harness.run(load(), label=args.label)
    path = report.write(res, REPORT_PATHS[args.label])
    for line in report.verdict_lines(res):
        print(line)
    print(f"Report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
