"""Agent signal separation (read-only analysis; never touches votes, weights or trades).

Question per agent: does gold behave differently after this agent's calls than at a random time?
  x = signed forward 4h move in the call's direction (BUY -> +move, SELL -> -move), divided by a scale
      (ATR at call time when a row carries one, else the baseline's std so the histogram bins fit).
  b = the same-horizon forward moves of ALL scored steps, both signs (a random direction).
  distance = Bhattacharyya distance(x, b); bootstrap 90% interval (resample both, seed 0).
Verdict: useful / harmful need n >= 30, interval lower bound above a noise floor, and mean(x) >/< 0.
Noise floor: 95th pct of the distance between two random halves of b (the first half sub-sampled to the
agent's n, so the floor carries the same small-sample bias as the agent's own distance).
Drift (both periods compared at the same sample size): last 30 days vs the 6 months before them; flagged when the interval of the difference excludes 0.
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
SIGN = {"BUY": 1.0, "SELL": -1.0}
BINS = np.linspace(-3, 3, 13)


def load_rows(db: Path = DB):
    """(rows, source): one scored step per hour (live, then 15m backtest, then 1h backtest win overlaps)."""
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


def _boot(x, b, rng, draws):
    out = np.empty(draws)
    for i in range(draws):
        out[i] = _dist(x[rng.integers(0, len(x), len(x))], b[rng.integers(0, len(b), len(b))])
    return out


def _floor(b, n, rng, draws):
    out = np.empty(draws)
    for i in range(draws):
        p = rng.permutation(len(b))
        h = len(b) // 2
        out[i] = _dist(b[p[:h]][:n], b[p[h:]])
    return float(np.percentile(out, 95))


def separation(rows, draws: int = 500, now: float | None = None, source: str = "") -> list[dict]:
    """rows: [(t, fwd_move, {agent: bias}[, atr])]. Returns one dict per agent."""
    if not rows:
        return []
    now = now if now is not None else max(r[0] for r in rows)
    ts = np.array([r[0] for r in rows], dtype=float)
    mv = np.array([r[1] for r in rows], dtype=float)
    atr = np.array([(r[3] if len(r) > 3 and r[3] else np.nan) for r in rows], dtype=float)
    scale = np.where(np.isnan(atr), np.std(mv) or 1.0, atr)
    norm = mv / scale
    base = np.concatenate([norm, -norm])
    out = []
    for ag in sorted({a for r in rows for a in r[2]}):
        sg = np.array([SIGN.get(r[2].get(ag, "WAIT"), 0.0) for r in rows])
        m = sg != 0
        x, tt = norm[m] * sg[m], ts[m]
        n = int(m.sum())
        rec = dict(agent=ag, n=n, mean=None, hit_rate=None, distance=None, lo=None, hi=None,
                   verdict="too_few", drift=None, source=source)
        out.append(rec)
        if n == 0:
            continue
        rng = np.random.default_rng(0)
        d = _dist(x, base)
        rec.update(mean=float(x.mean()), hit_rate=round(float((x > 0).mean()) * 100, 1), distance=float(d))
        if n < MIN_N:
            continue
        bs = _boot(x, base, rng, draws)
        lo, hi = float(np.percentile(bs, 5)), float(np.percentile(bs, 95))
        rec.update(lo=min(lo, d), hi=max(hi, d))
        rec["verdict"] = ("useful" if rec["mean"] > 0 else "harmful") if lo > _floor(base, n, rng, draws) and rec["mean"] != 0 else "none"
        rec["drift"] = _drift(x, tt, norm, ts, now, rng, draws)
    return out


def _drift(x, tt, norm, ts, now, rng, draws):
    """Each period is compared with ITS OWN baseline (all steps of that period, both signs), so a calmer or wilder
    market does not look like an agent changing; both sides use the same sample size (distance is biased up for small n)."""
    rm, pm = tt > now - 30 * DAY, (tt <= now - 30 * DAY) & (tt > now - 213 * DAY)
    xr, xp = x[rm], x[pm]
    if len(xr) < MIN_N or len(xp) < MIN_N:
        return None
    mr, mp = ts > now - 30 * DAY, (ts <= now - 30 * DAY) & (ts > now - 213 * DAY)
    br, bp = np.concatenate([norm[mr], -norm[mr]]), np.concatenate([norm[mp], -norm[mp]])
    k = min(len(xr), len(xp))
    drs, dps = np.empty(draws), np.empty(draws)
    for i in range(draws):
        drs[i] = _dist(xr[rng.integers(0, len(xr), k)], br[rng.integers(0, len(br), len(br))])
        dps[i] = _dist(xp[rng.integers(0, len(xp), k)], bp[rng.integers(0, len(bp), len(bp))])
    diffs = drs - dps
    lo, hi = float(np.percentile(diffs, 5)), float(np.percentile(diffs, 95))
    return dict(recent_n=int(len(xr)), prior_n=int(len(xp)), recent_distance=float(drs.mean()), prior_distance=float(dps.mean()),
                recent_mean=float(xr.mean()), prior_mean=float(xp.mean()), diff=float(diffs.mean()), lo=lo, hi=hi,
                flag=bool(lo > 0 or hi < 0))
