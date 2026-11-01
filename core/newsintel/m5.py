"""Five-minute break-of-structure and retest chips for the news card. Display only: never feeds votes or trades."""
from __future__ import annotations

from core.indicators import atr
from core.models import Candle
from core.structure import last_bos, zigzag

MIN_CANDLES = 30
RECENT = 6              # a break counts while it is within the last 6 bars
RETEST_ATR = 0.25       # the retest must come within this many ATR of the broken level


def _none(text: str) -> dict:
    return {"bos": None, "retest": None, "text": text}


def m5_confirmations(candles: list[Candle]) -> dict:
    """{"bos": "up"|"down"|None, "retest": "up"|"down"|None, "text": str} from finished 5-minute candles."""
    try:
        n = len(candles)
        if n < MIN_CANDLES:
            return _none("Not enough 5-minute candles")
        bos = last_bos(candles, zigzag(candles, 2.0))
        if bos is None or bos[0] < n - RECENT:
            return _none("No recent 5-minute break of structure")
        j, way, level = bos
        side = way.lower()
        a = atr(candles, 14)[-1] or 0.0
        tol = RETEST_ATR * a
        retest, lost = None, False
        for c in candles[j + 1:]:
            if (c.c <= level) if side == "up" else (c.c >= level):
                retest, lost = None, True          # closed back through the level: the break failed
            elif side == "up" and c.l <= level + tol or side == "down" and c.h >= level - tol:
                retest, lost = side, False
        text = f"5-minute break {side}"
        text += (" and retested the level, holding" if retest else
                 ", then closed back through the level" if lost else ", no retest yet")
        return {"bos": side, "retest": retest, "text": text}
    except Exception:  # noqa: BLE001 - display only, never raise
        return _none("Not enough 5-minute candles")
