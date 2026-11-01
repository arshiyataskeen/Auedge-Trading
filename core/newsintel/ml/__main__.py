"""CLI: python -m core.newsintel.ml [--label label60|label120] — runs the walk-forward, writes the report, prints the verdict."""
from __future__ import annotations

import argparse

from . import harness, report
from .data import load
from ..minutes import DATA

REPORT_PATHS = {"label60": DATA / "news_intel_report.html", "label120": DATA / "news_intel_report_120.html"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m core.newsintel.ml", description=__doc__)
    ap.add_argument("--label", choices=harness.LABELS, default="label60")
    args = ap.parse_args(argv)
    res = harness.run(load(), label=args.label)
    path = report.write(res, REPORT_PATHS[args.label])
    for line in report.verdict_lines(res):
        print(line)
    print(f"Report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
