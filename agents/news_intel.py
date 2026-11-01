"""News intelligence: the news picture around US releases (before / after, typical first-hour move, advisory chances,
similar past releases). Display only: never votes (weight 0, votes=False), always WAIT with confidence 0."""
from __future__ import annotations

import asyncio
import dataclasses
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

from core import news
from core.models import MarketContext
from core.newsintel.bars import NY
from core.newsintel.mode import effective_mode, mode

from .base import BaseAgent

TIMEOUT_S = 8.0                     # under the 10 s agent limit in agents/base.py
MODELS_DIR = Path(__file__).resolve().parent.parent / "data" / "news_intel" / "models"   # = ml.export.MODELS_DIR
META = "meta.json"
CHANCES = "Chances (advisory, not used for trades)"
_cache: dict = {}                   # {"mtime": float, "art": Artifacts | None}


def load_artifacts(path):
    from core.newsintel.ml.export import load_artifacts as load   # lazy: see build_intel_async
    return load(path)


async def build_intel_async(ctx, now, art, timeout=TIMEOUT_S):
    # imported here: core.newsintel.features imports agents.chief, so a top-level import would be circular
    from core.newsintel.live import build_intel_async as build
    return await build(ctx, now, art, timeout=timeout)


def artifacts():
    """The exported models, loaded once and reloaded when meta.json changes. Missing/unreadable -> None."""
    try:
        mtime = (Path(MODELS_DIR) / META).stat().st_mtime
    except OSError:
        _cache.clear()
        return None
    if _cache.get("mtime") != mtime:
        art = load_artifacts(MODELS_DIR)
        _cache.update(mtime=mtime, art=art)
    return _cache.get("art")


def jsonable(v):
    """numpy scalars/arrays -> plain Python, NaN/inf -> None, tuples -> lists (recursively)."""
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)):
        return [jsonable(x) for x in (v.tolist() if isinstance(v, np.ndarray) else v)]
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return f if math.isfinite(f) else None
    if v is None or isinstance(v, str):
        return v
    return str(v)


def _pct(p) -> str:
    return f"{100 * p:.0f}%"


def _gate(intel, art, now: float) -> str | None:
    """Why trading should be avoided right now (no-trade window around the release, or abnormal 5-minute range)."""
    ev = intel.event
    if ev:
        a, b = news.window({"kind": ev["kind"], "t": int(ev["t"])})
        if a <= now <= b:
            return f"inside the no-trade window around {ev['name']}"
    p99 = getattr(art, "m5_range_p99", None) if art is not None else None
    if intel.m5_ratio is not None and p99 and intel.m5_ratio > p99:
        return "the last 5-minute candle was unusually large"
    return None


def _when(t: int, now: float) -> str:
    ny = datetime.fromtimestamp(t, NY).strftime("%a %d %b %H:%M New York")
    mins = round((t - now) / 60)
    rel = (f"in {mins} min" if 0 <= mins < 120 else f"in {mins / 60:.1f} h" if mins >= 0
           else f"{-mins} min ago" if -mins < 120 else f"{-mins / 60:.1f} h ago")
    return f"{ny} ({rel})"


class NewsIntelAgent(BaseAgent):
    name, label, weight, votes = "news_intel", "News intelligence", 0, False

    async def analyze(self, ctx: MarketContext):
        if mode() == "off":
            return self.result(ctx, status="OK", bias="WAIT", confidence=0, headline="News intelligence is off",
                               bias_label="OFF", summary="News intelligence is switched off (NEWSINTEL_MODE=off).")
        art = await asyncio.to_thread(artifacts)   # first load unpickles the models (~2.5 s): keep the loop free
        eff = effective_mode(art)
        now = ctx.generated_at.timestamp()
        intel = await build_intel_async(ctx, now, art, timeout=TIMEOUT_S)
        warnings = list(intel.notes)
        if mode() == "live" and eff != "live":
            warnings.append("Live mode was requested, but the news models did not pass the go-live check, so this "
                            "stays advisory only.")
        ev = intel.event
        kind = (ev or {}).get("kind") or ""
        gate = _gate(intel, art, now)
        phase_word = {"pre": f"BEFORE {kind}", "post": f"AFTER {kind}"}.get(intel.phase, "NO NEWS")
        rows: list[list[str]] = []
        if ev:
            others = f" (also: {', '.join(intel.others)})" if intel.others else ""
            rows.append(["Next / last release", f"{ev['name']} - {_when(int(ev['t']), now)}{others}"])
        else:
            rows.append(["Next / last release", "No major US release in the next 24 hours"])
        if intel.expected_move is not None:
            txt = f"about ${intel.expected_move:.2f} (typical for this kind of release, does not say which way)"
            if intel.expected_range:
                lo, hi = intel.expected_range
                txt += f"; range {lo:,.2f} - {hi:,.2f}"
            rows.append(["Typical first-hour move", txt])
        elif ev:
            rows.append(["Typical first-hour move", "not available right now (see notes)"])
        if intel.probs:
            p = intel.probs
            rows.append([CHANCES, f"up {_pct(p.get('up', 0))} / flat {_pct(p.get('side', 0))} / "
                                  f"down {_pct(p.get('down', 0))}"])
        if ev:
            if intel.phase == "post":
                z = intel.surprise_z
                rows.append(["Surprise", "not known yet" if z is None else
                             f"{z:+.1f} (in standard deviations; {'bigger' if abs(z) >= 1 else 'small'} surprise)"])
            else:
                rows.append(["Surprise", "actual not published yet"])
            rows.append(["Similar past releases", f"{len(intel.similar)} found"])
            rows.append(["Model trust", f"go-live: {'yes' if intel.go_live else 'no - advisory only'}; "
                                        f"uncertain: {'yes' if intel.uncertain else 'no'}"])

        if not ev:
            summary = "No major US release in the next 24 hours, so there is no news context."
            headline = "No news context"
        else:
            headline = f"{ev['name']}: {'before' if intel.phase == 'pre' else 'after'} the release"
            parts = [f"{ev['name']} {_when(int(ev['t']), now)}."]
            if intel.expected_move is not None:
                parts.append(f"A typical first hour after this kind of release moves gold about "
                             f"${intel.expected_move:.2f}.")
            if gate:
                parts.append(f"Avoid new trades: {gate}.")
            if intel.probs:
                if intel.uncertain:
                    parts.append("The up/flat/down chances are close to even and uncertain: advisory only, not a "
                                 "trade signal.")
                else:
                    parts.append("The up/flat/down chances are advisory only and are not used for trades.")
            summary = " ".join(parts)
        try:
            extra = jsonable(dataclasses.asdict(intel)) | {"mode": eff}
        except Exception as e:  # noqa: BLE001 - the card must still show
            print(f"[news_intel] extra not serialisable: {type(e).__name__}: {e}", file=sys.stderr)
            extra = {"mode": eff}
        return self.result(ctx, status="OK", bias="WAIT", confidence=0, headline=headline,
                           bias_label="AVOID" if gate else phase_word, subtitle=f"mode: {eff}",
                           rows=rows, summary=summary, warnings=warnings, extra=extra)
