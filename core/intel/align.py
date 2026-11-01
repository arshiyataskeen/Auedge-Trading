"""H1 structure + M15 trend alignment."""
from __future__ import annotations

from dataclasses import dataclass

from core.models import Candle
from core.structure import tf_bias


@dataclass
class Alignment:
    state: str = "mixed"      # aligned_up | aligned_down | mixed
    h1: str = "n/a"
    m15: str = "n/a"
    text: str = ""


def align_state(h1_dir: int, m15_dir: int) -> str:
    return "aligned_up" if h1_dir > 0 and m15_dir > 0 else "aligned_down" if h1_dir < 0 and m15_dir < 0 else "mixed"


def alignment(h1: list[Candle], m15: list[Candle]) -> Alignment:
    """`h1`/`m15` closed candles. H1 direction = swing structure (UP/DOWN); M15 = its bias."""
    if len(h1) < 60 or len(m15) < 60:
        return Alignment(text="Not enough 1H/15m candles to judge alignment.")
    i1, i15 = tf_bias(h1, 2.0), tf_bias(m15, 2.0)
    d1 = {"UP": 1, "DOWN": -1}.get(i1["state"], 0)
    d15 = 1 if "BUY" in i15["bias"] else -1 if "SELL" in i15["bias"] else 0
    st = align_state(d1, d15)
    w = {1: "up", -1: "down", 0: "sideways"}
    txt = {"aligned_up": "1H structure and 15m trend both point up.",
           "aligned_down": "1H structure and 15m trend both point down.",
           "mixed": f"1H is {w[d1]} and 15m is {w[d15]}: not aligned."}[st]
    return Alignment(st, w[d1], w[d15], txt)


def opposes(st: str, side: str) -> bool:
    return (st == "aligned_down" and side == "BUY") or (st == "aligned_up" and side == "SELL")
