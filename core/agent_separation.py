"""Agent signal separation (read-only analysis; never touches votes, weights or trades).

Question per agent: does gold behave differently after this agent's calls than at a random time?
  x = signed forward 4h move in the call's direction (BUY -> +move, SELL -> -move), divided by a scale
      (ATR at call time when a row carries one, else the baseline's std so the histogram bins fit).
  b = the same-horizon forward moves of ALL scored steps, both signs (a random direction).
  distance = Bhattacharyya distance(x, b).
Intervals use a moving-block bootstrap (block 8, time-ordered) because neighbouring steps share 4h windows.
Noise floor: 95th pct of the distance between b and contiguous random runs of b with the same lengths as the
agent's own call runs (random sign per run), so n and clustering match.
Verdict: useful / harmful need n >= 30, the distance's 90% lower bound above the noise floor, AND the block-bootstrap
90% interval of mean(x) to exclude 0 in that direction. Otherwise "none"; n < 30 is "too_few".
Drift (same sample size, each period vs its own baseline): last 30 days vs the 6 months before; flagged when the
95% interval of the difference excludes 0 (a few false flags are expected across many agents).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

from core.newsintel.ml.stats import bhattacharyya

DB = Path(__file__).resolve().parent.parent / "data" / "dataset.db"
DAY = 86400
MIN_N = 30
BLOCK = 8
SIGN = {"BUY": 1.0, "SELL": -1.0}
BINS = np.linspace(-3, 3, 13)


def load_rows(db: Path = DB):
    """(rows, source): one scored step per hour (live, then 15m backtest, then 1h backtest win overlaps)."""
    if not Path(db).is_file():
        raise FileNotFoundError(str(db))
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        q = ("SELECT src, t, fwd_4h, agents FROM steps WHERE fwd_4h IS NOT NULL ORDER BY "
             "CASE src WHEN 'live' THEN 0 WHEN 'backtest_15m' THEN 1 ELSE 2 END, t")
        seen, out, srcs = set(), [], set()
        for src, t, fwd, agents in con.execute(q):
            if t // 3600 in seen:
                continue
            seen.add(t // 3600)
            out.append((int(t), float(fwd), {k: (v or {}).get("bias", "WAIT") for k, v in json.loads(agents).items()}))
            srcs.add(src)
    finally:
        con.close()
    out.sort(key=lambda r: r[0])
    return out, "dataset.db steps (" + " + ".join(sorted(srcs)) + ", 4h forward move, one step per hour)"


def _dist(x, b):
    return bhattacharyya(x, b, BINS)


def _blocks(a, rng, n=None):
    """Moving-block bootstrap resample of a time-ordered array (blocks of BLOCK consecutive values)."""
    n = len(a) if n is None else n
    k = min(BLOCK, len(a))
    starts = rng.integers(0, len(a) - k + 1, -(-n // k))
    return np.concatenate([a[i:i + k] for i in starts])[:n]


def _sym(a):
    return np.concatenate([a, -a])


def _runs(m):
    """Lengths of maximal runs of consecutive True in a boolean mask."""
    idx = np.flatnonzero(np.diff(np.concatenate([[0], m.astype(int), [0]])))
    return (idx[1::2] - idx[::2]).tolist()


def _floor(norm, runs, base, rng, draws):
    out = np.empty(draws)
    for i in range(draws):
        parts = []
        for L in runs:
            L = min(L, len(norm))
            s0 = int(rng.integers(0, len(norm) - L + 1))
            parts.append(norm[s0:s0 + L] * (1.0 if rng.random() < .5 else -1.0))
        out[i] = _dist(np.concatenate(parts), base)
    return float(np.percentile(out, 95))


def separation(rows, draws: int = 500, now: float | None = None, source: str = "") -> list[dict]:
    """rows: [(t, fwd_move, {agent: bias}[, atr])]. Returns one dict per agent."""
    if not rows:
        return []
    rows = sorted(rows, key=lambda r: r[0])
    now = now if now is not None else max(r[0] for r in rows)
    ts = np.array([r[0] for r in rows], dtype=float)
    mv = np.array([r[1] for r in rows], dtype=float)
    atr = np.array([(r[3] if len(r) > 3 and r[3] else np.nan) for r in rows], dtype=float)
    scale = np.where(np.isnan(atr), np.std(mv) or 1.0, atr)
    norm = mv / scale
    base = _sym(norm)
    out = []
    for ag in sorted({a for r in rows for a in r[2]}):
        sg = np.array([SIGN.get(r[2].get(ag, "WAIT"), 0.0) for r in rows])
        m = sg != 0
        x, tt = norm[m] * sg[m], ts[m]
        n = int(m.sum())
        rec = dict(agent=ag, n=n, mean=None, mean_lo=None, mean_hi=None, hit_rate=None, distance=None, lo=None, hi=None,
                   verdict="too_few", drift=None, source=source)
        out.append(rec)
        if n == 0:
            continue
        rng = np.random.default_rng(0)
        d = _dist(x, base)
        rec.update(mean=float(x.mean()), hit_rate=round(float((x > 0).mean()) * 100, 1), distance=float(d))
        if n < MIN_N:
            continue
        bd, bm = np.empty(draws), np.empty(draws)
        for i in range(draws):
            xs = _blocks(x, rng)
            bd[i] = _dist(xs, _sym(_blocks(norm, rng)))
            bm[i] = xs.mean()
        lo, hi = float(np.percentile(bd, 5)), float(np.percentile(bd, 95))
        mlo, mhi = float(np.percentile(bm, 5)), float(np.percentile(bm, 95))
        rec.update(lo=min(lo, d), hi=max(hi, d), mean_lo=mlo, mean_hi=mhi)
        if lo > _floor(norm, _runs(m), base, rng, draws):
            rec["verdict"] = "useful" if mlo > 0 else "harmful" if mhi < 0 else "none"
        else:
            rec["verdict"] = "none"
        rec["drift"] = _drift(x, tt, norm, ts, now, rng, draws)
    return out


def _drift(x, tt, norm, ts, now, rng, draws):
    """Each period vs ITS OWN baseline (all steps of that period, both signs), same sample size on both sides
    (the distance is biased up for small n); moving-block bootstrap, 95% interval."""
    rm, pm = tt > now - 30 * DAY, (tt <= now - 30 * DAY) & (tt > now - 213 * DAY)
    xr, xp = x[rm], x[pm]
    if len(xr) < MIN_N or len(xp) < MIN_N:
        return None
    mr, mp = ts > now - 30 * DAY, (ts <= now - 30 * DAY) & (ts > now - 213 * DAY)
    nr, npr = norm[mr], norm[mp]
    k = min(len(xr), len(xp))
    drs, dps = np.empty(draws), np.empty(draws)
    for i in range(draws):
        drs[i] = _dist(_blocks(xr, rng, k), _sym(_blocks(nr, rng)))
        dps[i] = _dist(_blocks(xp, rng, k), _sym(_blocks(npr, rng)))
    diffs = drs - dps
    lo, hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
    return dict(recent_n=int(len(xr)), prior_n=int(len(xp)), recent_distance=float(drs.mean()), prior_distance=float(dps.mean()),
                recent_mean=float(xr.mean()), prior_mean=float(xp.mean()), diff=float(diffs.mean()), lo=lo, hi=hi,
                flag=bool(lo > 0 or hi < 0))
