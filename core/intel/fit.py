"""Fit volatility/entry thresholds from the 1-minute backup: `python -m core.intel.fit [--until YYYY-MM-DD]`.

Only data before --until is used (default 2025-08-01, the final-year holdout). Writes data/intel_params.json.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from core.intel.entry import fit_entry
from core.intel.volatility import PARAMS_PATH, fit_vol
from core.newsintel import bars
from core.newsintel.minutes import DATA, load_backup_minutes


def fit_all(until: str = "2025-08-01") -> dict:
    u = int(datetime.fromisoformat(until).replace(tzinfo=timezone.utc).timestamp())
    m = load_backup_minutes(DATA / "none.bak")      # backup gone: uses the cached xau_1m.npz
    cs = bars.resample(m, 900, u, 10**7)
    return {"until": until, "vol": fit_vol(cs, u), "entry": fit_entry(cs, u)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default="2025-08-01")
    out = fit_all(ap.parse_args().until)
    PARAMS_PATH.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
