"""Structure quality (closed 15m candles only): stop-hunt sweep, then a candle-CLOSE break of structure within N bars.

Also reports displacement (body >= 0.6 of range and range >= 1.2 x ATR14), breakout body strength (0..1) and a
failed-breakout check (a close back inside the broken level within 3 bars). Pure; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.indicators import atr

N_BARS, FAIL_BARS = 8, 3


@dataclass
class StructureQ:
    swept: bool = False
    bos: bool = False
    ok: bool = False              # sweep then BOS within N bars, and the break did not fail
    displacement: bool = False
    body_strength: float = 0.0    # breakout candle body / range (0..1)
    failed: bool = False
    text: str = ""


def analyze(candles, side: str, n: int = N_BARS) -> StructureQ:
    from core.structure import confirmed, zigzag
    try:
        if len(candles) < 30:
            return StructureQ(text="Not enough closed candles to judge structure.")
        up = side == "BUY"
        a = atr(candles)
        piv = confirmed(zigzag(candles, 2.0))
        last = len(candles) - 1
        out = StructureQ(text="No stop hunt followed by a break.")
        for p in reversed([p for p in piv if p.kind == ("L" if up else "H")]):
            # sweep: a wick through the swing that closes back on the right side
            j = next((j for j in range(p.i + 1, len(candles))
                      if (candles[j].l < p.price and candles[j].c > p.price if up
                          else candles[j].h > p.price and candles[j].c < p.price)), None)
            if j is None or j < last - n - 3:
                continue
            out.swept = True
            lvl = [q for q in piv if q.kind == ("H" if up else "L") and q.i < j]
            if not lvl:
                continue
            lv = lvl[-1].price
            k = next((k for k in range(j, min(j + n, last) + 1)
                      if (candles[k].c > lv if up else candles[k].c < lv)), None)
            if k is None:
                continue
            c = candles[k]
            rng = c.h - c.l
            out.bos = True
            out.body_strength = round(min(1.0, abs(c.c - c.o) / rng), 2) if rng else 0.0
            ar = a[k] or 0
            out.displacement = bool(rng and ar and abs(c.c - c.o) >= 0.6 * rng and rng >= 1.2 * ar
                                    and (c.c - c.o) * (1 if up else -1) > 0)
            out.failed = any((x.c < lv if up else x.c > lv) for x in candles[k + 1:k + 1 + FAIL_BARS])
            out.ok = out.bos and not out.failed and k >= last - n
            d = "up" if up else "down"
            out.text = ("The break failed: price closed back inside the broken level." if out.failed
                        else f"Stops were hunted and 15m then closed {d} through structure"
                             f"{' with a strong candle' if out.displacement else ''}." if out.ok
                        else "Stop hunt seen and a break, but it is not recent.")
            return out
        if out.swept:
            out.text = "Stop hunt seen, but no 15m close through structure yet."
        return out
    except Exception:  # noqa: BLE001
        return StructureQ(text="Structure check not available.")
