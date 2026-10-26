"""Offline tuning on the recorded 6-month replay (data/research/steps_6m.pkl): no agents are re-run.

TRAIN = up to 2026-09-20, TEST = 2026-09-21 onwards (touched once, at the end).
1. Agent diagnostics on TRAIN (4-hour $3 hit rate by month / session / regime, agreement vs trade result,
   Market psychology extremes and trapped-trader signals).
2. Two-stage grid on TRAIN: entry filters first (with the current exits), then exit rules on the best entry sets.
3. Baseline + top 3 evaluated once on TEST.
Run: .venv\\Scripts\\python.exe research\\tune.py   -> data/research/tuning_report.md and tuning_results.json
"""
import json
import pickle
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "research"
NY = ZoneInfo("America/New_York")
SPLIT = int(datetime(2026, 9, 21, tzinfo=timezone.utc).timestamp())
COST = 0.30
PENDING_S, EXPIRY_S = 8 * 3600, 24 * 3600
BASE_W = {"wyckoff": 1.5, "elliott": 1.0, "smc": 1.5, "price_action": 1.5, "trend": 1.5, "macro": 1.0,
          "sentiment": 1.0, "skeptic": 0.75}

d = pickle.load((DATA / "steps_6m.pkl").open("rb"))
STEPS, EX = d["steps"], d["ex"]                      # ex: (t, o, h, l, c, sec)
EX_END = [t + s for t, o, h, l, c, s in EX]


def side_of(b):
    return 1 if "BUY" in (b or "") else -1 if "SELL" in (b or "") else 0


def session(T):
    h = datetime.fromtimestamp(T, timezone.utc).hour
    return "London" if 7 <= h < 12 else "New York" if 12 <= h < 21 else "Asia"


def ny_day(T):
    from datetime import timedelta
    return (datetime.fromtimestamp(T, NY) + timedelta(hours=6)).strftime("%Y-%m-%d")


def price_at(T):
    j = bisect_left(EX_END, T)
    return EX[j][4] if j < len(EX) else None


# ------------------------------------------------------------------ diagnostics
def hit_table(steps):
    """Per agent: 4h move in the call's direction; hit >= $3, miss <= -$3."""
    out = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))   # agent -> bucket -> [hit, miss, flat]
    for st in steps:
        p4 = price_at(st["T"] + 4 * 3600)
        if p4 is None:
            continue
        month = datetime.fromtimestamp(st["T"], timezone.utc).strftime("%Y-%m")
        d1 = st["tfs"].get("Daily", "")
        regime = "trend" if d1 in ("BUY", "SELL") else "range/lean"
        calls = [(k, a["bias"]) for k, a in st["agents"].items() if a["status"] == "OK" and a["bias"] in ("BUY", "SELL")]
        sd = 1 if st["score"] >= .15 else -1 if st["score"] <= -.15 else 0
        if sd:
            calls.append(("chief", "BUY" if sd > 0 else "SELL"))
        for k, b in calls:
            mv = (p4 - st["price"]) * side_of(b)
            idx = 0 if mv >= 3 else 1 if mv <= -3 else 2
            for bucket in ("all", month, session(st["T"]), regime):
                out[k][bucket][idx] += 1
    return out


def rate(x):
    return round(100 * x[0] / (x[0] + x[1])) if x[0] + x[1] else None


def psych_table(steps):
    """Market psychology: mood extremes and its directional signals, 4h and 12h forward."""
    rows = defaultdict(lambda: [0, 0, 0.0, 0])          # name -> [hit4, miss4, sum12, n]
    for st in steps:
        a = st["agents"].get("sentiment")
        if not a or a["status"] != "OK":
            continue
        p4, p12 = price_at(st["T"] + 4 * 3600), price_at(st["T"] + 12 * 3600)
        if p4 is None or p12 is None:
            continue
        mood = a["metrics"].get("mood")
        # mood extremes read contrarian: greed/euphoria -> expect down, fear/panic -> expect up
        if mood in ("GREED", "EUPHORIA", "FEAR", "PANIC"):
            s = -1 if mood in ("GREED", "EUPHORIA") else 1
            r = rows[f"mood {mood} (contrarian)"]
            mv = (p4 - st["price"]) * s
            r[0] += mv >= 3; r[1] += mv <= -3; r[2] += (p12 - st["price"]) * s; r[3] += 1
        if a["bias"] in ("BUY", "SELL"):
            name = "exhaustion fade (conf 65)" if a["conf"] >= 65 else "trapped traders (conf 50)"
            s = side_of(a["bias"])
            r = rows[name]
            mv = (p4 - st["price"]) * s
            r[0] += mv >= 3; r[1] += mv <= -3; r[2] += (p12 - st["price"]) * s; r[3] += 1
    return rows


# ------------------------------------------------------------------ simulator
def weighted_net(st, weights):
    tot = net = 0.0
    for k, a in st["agents"].items():
        w = weights.get(k, 0)
        if a["status"] != "OK" or not w:
            continue
        tot += w * 100
        if a["bias"] in ("BUY", "SELL"):
            net += w * a["conf"] * side_of(a["bias"])
    return net / tot if tot else 0


def allowed(st, p, weights):
    pl = st["plan"]
    if st["veto"] or pl["kind"] not in p["kinds"] or not pl["stop"] or not pl["t1"]:
        return False
    s = side_of(pl["side"])
    if st["conf"] < p["min_conf"]:
        return False
    if p["htf"] and not (side_of(st["tfs"].get("Daily")) == s and side_of(st["tfs"].get("4H")) == s):
        return False
    if p["zone"]:
        tr = st["agents"].get("trend")
        zp = tr and tr["status"] == "OK" and tr["metrics"].get("zone_pos")
        if isinstance(zp, (int, float)) and ((s > 0 and zp > 50) or (s < 0 and zp < 50)):
            return False
    if p["vote"] and weighted_net(st, weights) * s <= 0:
        return False
    if p["session"] == "LN" and session(st["T"]) == "Asia":
        return False
    ny = datetime.fromtimestamp(st["T"], NY)
    if p["fri"] and ny.weekday() == 4 and ny.hour >= 12:
        return False
    return True


def levels(pl, fill, s, p):
    risk0 = abs((pl["entry_lo"] + pl["entry_hi"]) / 2 - pl["stop"]) or 1
    stop = fill - s * p["stop_k"] * risk0
    risk = abs(fill - stop)
    tgt = pl["t1"] if p["target"] == "plan" else fill + s * p["target"] * risk
    return stop, tgt, risk


def simulate(steps, p, weights, t0=0, t1=10 ** 12):
    trades, trade, pend, per_day = [], None, None, defaultdict(int)
    by_n = {st["n"]: st for st in steps if t0 <= st["T"] < t1}
    first_n = min(by_n) if by_n else 0
    last_n = max(by_n) if by_n else -1
    for n in range(first_n, len(EX)):
        t, o, h, l, c, sec = EX[n]
        if n > last_n + 400 and not trade:
            break
        if trade and trade["entry_t"] <= t:                   # manage the open trade on this candle
            s = trade["s"]
            px = why = None
            if (o - trade["stop"]) * s <= 0: px, why = o, "stop"
            elif (o - trade["tgt"]) * s >= 0: px, why = o, "target"
            elif (l <= trade["stop"]) if s > 0 else (h >= trade["stop"]): px, why = trade["stop"], "stop"
            elif p["partial"] and not trade["half"] and ((h >= trade["one_r"]) if s > 0 else (l <= trade["one_r"])):
                trade["half"] = True
                trade["banked"] = 0.5 * ((trade["one_r"] - s * COST - trade["fill"]) * s / trade["risk"])
                trade["stop"] = trade["fill"]                 # breakeven on the rest
                if (h >= trade["tgt"]) if s > 0 else (l <= trade["tgt"]):
                    px, why = trade["tgt"], "target"
            elif (h >= trade["tgt"]) if s > 0 else (l <= trade["tgt"]): px, why = trade["tgt"], "target"
            if px is None and t + sec >= trade["entry_t"] + EXPIRY_S:
                px, why = c, "expired"
            if px is not None:
                r = (px - s * COST - trade["fill"]) * s / trade["risk"]
                trade["r"] = round(trade["banked"] + (0.5 if trade["half"] else 1) * r, 3)
                trade["why"] = why
                trades.append(trade)
                trade = None
        if pend and not trade:                                  # waiting order (plan's own rule)
            pl, s = pend["pl"], pend["s"]
            lvl = pl["entry_hi"] if s > 0 else pl["entry_lo"]
            if (c - pl["stop"]) * s < 0 or t + sec - pend["T"] >= PENDING_S:
                pend = None
            else:
                if (l < lvl) if s > 0 else (h > lvl):
                    pend["pierced"] = True
                if pend["pierced"] and (c - lvl) * s > 0:
                    trade = open_trade(pl, s, c, t + sec, p, pend["st"])
                    pend = None
        st = by_n.get(n)
        if st is None or trade:
            continue
        sd = 1 if st["score"] >= .15 else -1 if st["score"] <= -.15 else 0
        if pend and sd != pend["s"]:
            pend = None
        if not allowed(st, p, weights) or per_day[ny_day(st["T"])] >= p["max_day"]:
            continue
        pl, s = st["plan"], side_of(st["plan"]["side"])
        if pl["kind"] == "now" and n + 1 < len(EX):
            trade = open_trade(pl, s, EX[n + 1][1], EX[n + 1][0], p, st)
            if trade:
                per_day[ny_day(st["T"])] += 1
            pend = None
        elif pl["kind"] == "pending" and not pend:
            pend = {"pl": pl, "s": s, "T": st["T"], "pierced": False, "st": st}
            per_day[ny_day(st["T"])] += 1
    return trades


def open_trade(pl, s, price, t, p, st):
    fill = price + s * COST
    stop, tgt, risk = levels(pl, fill, s, p)
    if (fill - stop) * s <= 0 or (fill - tgt) * s >= 0:
        return None
    return {"s": s, "side": pl["side"], "kind": pl["kind"], "fill": fill, "stop": stop, "tgt": tgt, "risk": risk,
            "one_r": fill + s * risk, "entry_t": t, "half": False, "banked": 0.0, "T": st["T"], "conf": st["conf"],
            "biases": {k: a["bias"] for k, a in st["agents"].items() if a["status"] == "OK"}}


def stats(trades):
    rs = [x["r"] for x in trades]
    eq = peak = dd = 0.0
    streak = worst = 0
    for r in rs:
        eq += r; peak = max(peak, eq); dd = max(dd, peak - eq)
        streak = streak + 1 if r < 0 else 0; worst = max(worst, streak)
    n = len(rs)
    return {"n": n, "win": round(100 * sum(r > 0 for r in rs) / n) if n else None, "total": round(sum(rs), 2),
            "avg": round(sum(rs) / n, 3) if n else None, "dd": round(dd, 2), "streak": worst}


BASE = {"kinds": ("now", "pending"), "min_conf": 0, "htf": False, "zone": False, "vote": False, "session": "all",
        "fri": False, "max_day": 99, "stop_k": 1.0, "target": "plan", "partial": False}


def score(s):
    return s["total"] - 0.5 * s["dd"] if s["n"] >= 30 else -1e9


def main():
    train = [s for s in STEPS if s["T"] < SPLIT]
    test = [s for s in STEPS if s["T"] >= SPLIT]
    report = {"n_train_steps": len(train), "n_test_steps": len(test)}

    # ---- diagnostics (TRAIN only)
    ht = hit_table(train)
    report["hits"] = {k: {b: rate(v) for b, v in bk.items()} | {"_n": sum(bk["all"][:2])} for k, bk in ht.items()}
    tuned_w = {k: (0 if (report["hits"].get(k, {}).get("all") or 50) < 49 and report["hits"].get(k, {}).get("_n", 0) >= 200
                   else w) for k, w in BASE_W.items()}
    report["tuned_weights"] = tuned_w
    report["psych"] = {k: {"n": v[3], "hit4": rate(v), "avg12": round(v[2] / v[3], 2) if v[3] else None}
                       for k, v in psych_table(train).items()}

    base_tr = simulate(train, BASE, BASE_W, 0, SPLIT)
    agree = defaultdict(lambda: defaultdict(list))
    for t in base_tr:
        for k, b in t["biases"].items():
            rel = "agrees" if side_of(b) == t["s"] else "against" if side_of(b) == -t["s"] else "wait"
            agree[k][rel].append(t["r"])
    report["agree"] = {k: {rel: {"n": len(v), "total": round(sum(v), 2)} for rel, v in rr.items()} for k, rr in agree.items()}

    # ---- stage A: entry filters with current exits
    A = []
    for kinds, mc, htf, zone, vote, sess in product([("now", "pending"), ("now",)], [0, 60, 70], [False, True],
                                                    [False, True], [False, True], ["all", "LN"]):
        p = {**BASE, "kinds": kinds, "min_conf": mc, "htf": htf, "zone": zone, "vote": vote, "session": sess,
             "fri": True, "max_day": 2}
        s = stats(simulate(train, p, tuned_w, 0, SPLIT))
        A.append((score(s), p, s))
    A.sort(key=lambda x: -x[0])
    # ---- stage B: exits on the 5 best entry sets
    B = []
    for _, pa, _ in A[:5]:
        for k, tg, part in product([1.0, 1.3], ["plan", 1.5, 2.0, 2.5], [False, True]):
            p = {**pa, "stop_k": k, "target": tg, "partial": part}
            s = stats(simulate(train, p, tuned_w, 0, SPLIT))
            B.append((score(s), p, s))
    B.sort(key=lambda x: -x[0])
    top, seen = [], set()
    for sc, p, s in B:
        key = json.dumps(p, sort_keys=True)
        if key not in seen:
            seen.add(key); top.append((p, s))
        if len(top) == 3:
            break
    report["grid_size"] = len(A) + len(B)
    report["stageA_top"] = [{"params": p, "train": s} for _, p, s in A[:5]]

    # ---- TEST, once: baseline + top 3
    cands = [("baseline (current rules)", BASE, BASE_W)] + [(f"tuned #{i + 1}", p, tuned_w) for i, (p, _) in enumerate(top)]
    report["final"] = []
    for name, p, w in cands:
        tr = stats(simulate(train, p, w, 0, SPLIT))
        te_trades = simulate(test, p, w, SPLIT, 10 ** 12)
        report["final"].append({"name": name, "params": p, "train": tr, "test": stats(te_trades),
                                "test_trades": [{"T": t["T"], "side": t["side"], "kind": t["kind"], "r": t["r"],
                                                 "why": t["why"]} for t in te_trades]})
    (DATA / "tuning_results.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({"final": [{k: v for k, v in f.items() if k != "test_trades"} for f in report["final"]],
                      "tuned_weights": tuned_w, "grid": report["grid_size"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
