"""AuEdge: XAUUSD analysis dashboard server. Start with run.bat (or: python -m uvicorn app:app --port 8000)."""
import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, Query
from fastapi.responses import FileResponse

from agents import DATA_CHECK, PSYCH, all_agents
from agents.base import run_agent
from agents.chief import chief, today_view
from agents.psychology import apply_to_plan
from core import ai_summary, auth, dataset, track, trade_review, votes, webapp, weights as aw
from core.data import build_context, live_spot
from core.env import load_env

load_env()

STATIC = Path(__file__).parent / "static"
ANALYSIS_EVERY_S = 15 * 60          # full re-analysis at every 15m candle close (or on "Refresh now")
RUN_DELAY_S = 20                    # run this long after the candle closes, so the closed candle is in the data
VIEWED_WINDOW_S = 20 * 60           # Claude writes the verdict only if the page was open recently (API cost)
_last: dict = {"at": 0.0, "report": None, "viewed": 0.0}
_lock = asyncio.Lock()


def next_run_in() -> float:
    """Seconds until the next scheduled analysis (20 s after each :00, :15, :30, :45 candle close)."""
    now = time.time()
    return (now - RUN_DELAY_S) // ANALYSIS_EVERY_S * ANALYSIS_EVERY_S + ANALYSIS_EVERY_S + RUN_DELAY_S - now


async def _update(use_ai: bool) -> None:
    _last["report"] = await run_analysis(use_ai)
    _last["at"] = time.time()


RETRY_S = 60                        # a run with no live price (no internet, e.g. just after the PC wakes) is retried


def _data_failed() -> bool:
    rep = _last.get("report")
    return rep is not None and rep.get("spot") is None


async def _scheduler() -> None:
    """Runs the analysis on every 15m candle close, even when no page is open (keeps the track record going).
    Checks the wall clock every 15 s (one long sleep can fire hours late after the PC sleeps), and retries a run
    that had no live data after RETRY_S instead of waiting for the next candle."""
    while True:
        due = time.time() + next_run_in()
        while time.time() < due:
            if _data_failed() and time.time() - _last["at"] >= RETRY_S:
                break
            if _last["at"] and time.time() - _last["at"] > ANALYSIS_EVERY_S + 60:   # missed a slot (PC was asleep)
                break
            await asyncio.sleep(min(15, max(0.5, due - time.time())))
        try:
            async with _lock:
                await _update(time.time() - _last["viewed"] < VIEWED_WINDOW_S)
        except Exception as e:  # noqa: BLE001 - one failed run must not stop the schedule
            print(f"[scheduler] {type(e).__name__}: {e}")
            await asyncio.sleep(RETRY_S)


HISTORY_EVERY_S = 6 * 3600         # save new candles to the backtest history (the free feed keeps only ~1 month of 15m)


async def _history_saver() -> None:
    """Merges fresh candles into data/backtest_cache every 6 hours, so the 15m history keeps growing with no gaps."""
    from backtest import load_data
    while True:
        try:
            await asyncio.to_thread(load_data, False, False)    # downloads only series older than 6 hours
        except BaseException as e:  # noqa: BLE001 - load_data exits on a first-ever failed download; try again later
            if isinstance(e, asyncio.CancelledError):
                raise
            print(f"[history] {type(e).__name__}: {e}")
        await asyncio.sleep(HISTORY_EVERY_S)


async def _daily_backup() -> None:
    """Once a day (and shortly after AuEdge starts): readable CSV exports + a zipped copy of all records (core/backup.py)."""
    from core import backup
    await asyncio.sleep(60)
    while True:
        try:
            await asyncio.to_thread(backup.daily)
        except Exception as e:  # noqa: BLE001 - never stop the app over a backup
            print(f"[backup] {type(e).__name__}: {e}")
        await asyncio.sleep(6 * 3600)          # checks 4x a day; makes at most one zip per day


REVIEW_EVERY_S = 7 * 86400


async def _review_scheduler() -> None:
    """Weekly review board, in the background at low priority: at the weekend (gold is closed), or on any day once
    a review is more than 9 days overdue (e.g. the PC was off all weekend). Never while another test is running."""
    from datetime import datetime
    await asyncio.sleep(120)
    while True:
        try:
            last = _review_latest()
            age = time.time() - (last["made_at"] if last else 0)
            weekend = datetime.now().weekday() >= 5
            busy = _bt["proc"] and _bt["proc"].poll() is None
            if not busy and age > REVIEW_EVERY_S and (weekend or age > 9 * 86400):
                review_run(False)
        except Exception as e:  # noqa: BLE001 - try again next hour
            print(f"[review] {type(e).__name__}: {e}")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(_app):
    tasks = [asyncio.create_task(_scheduler()), asyncio.create_task(_history_saver()),
             asyncio.create_task(_review_scheduler()), asyncio.create_task(_daily_backup())]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="AuEdge (XAUUSD analysis)", lifespan=lifespan)
# Password login, only when AUEDGE_PASSWORD is set (the online version); on your own PC it stays open.
app.middleware("http")(auth.middleware)
app.get("/login", include_in_schema=False)(lambda: auth.page())
app.post("/login", include_in_schema=False)(auth.login)
app.get("/logout", include_in_schema=False)(auth.logout)



NO_CACHE = {"Cache-Control": "no-cache"}   # the browser always checks for a newer version (a cheap 304 when unchanged)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers=NO_CACHE)


APP_FILES = {"icon.svg": "image/svg+xml", "apple-touch-icon.png": "image/png", "icon-192.png": "image/png",
             "icon-512.png": "image/png", "manifest.webmanifest": "application/manifest+json",
             "journal.js": "text/javascript"}


app.include_router(webapp.router)   # React app at /app/* (before the catch-all below)


@app.get("/{name}")
def app_file(name: str):
    """Icons and the web-app manifest (for 'Add to Home Screen' on iPhone and Android)."""
    if name not in APP_FILES:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    return FileResponse(STATIC / name, media_type=APP_FILES[name], headers=NO_CACHE if name.endswith((".js", ".webmanifest")) else None)


_weights: dict = {"week": None, "mult": {}}
# Performance weights are computed and shown, but only used when turned on (in the 4-month walk-forward test they did
# slightly worse than fixed weights). Turn on with USE_PERFORMANCE_WEIGHTS=1 in .env.
USE_PERF_WEIGHTS = os.getenv("USE_PERFORMANCE_WEIGHTS", "0") == "1"


def weekly_multipliers() -> tuple[int, dict]:
    """This week's performance multipliers from the live track record (recomputed once per trading week)."""
    wk = aw.week_start(time.time())
    if _weights["week"] != wk:
        try:
            scored = [r for r in track.scored_calls(wk - aw.WINDOW_S) if r[1] + track.HORIZON_S <= wk]
            _weights.update(week=wk, mult=aw.multipliers(scored, wk))
        except Exception as e:  # noqa: BLE001 - fall back to the default weights
            print(f"[weights] {e}")
            _weights.update(week=wk, mult={})
    return wk, _weights["mult"]


def _apply_news_hook(report, results) -> None:
    """News view on the Chief's report; any failure (even the import) leaves the report untouched."""
    try:
        from core.newsintel.chief_hook import apply_from_results
        apply_from_results(report, results)
    except Exception as e:  # noqa: BLE001
        print(f"[news_intel] chief hook skipped: {type(e).__name__}: {e}")


async def run_analysis(use_ai: bool = True) -> dict:
    ctx = await build_context("15m")
    agents, adapter_problems = all_agents()
    stage1 = [a for a in agents if getattr(a, "stage", 1) == 1]
    stage2 = [a for a in agents if getattr(a, "stage", 1) == 2]
    results = list(await asyncio.gather(*(run_agent(a, ctx) for a in stage1)))
    ctx.prior = results
    results += await asyncio.gather(*(run_agent(a, ctx) for a in stage2))
    check = await run_agent(DATA_CHECK, ctx)
    base = {a.name: (a.weight if a.votes else 0) for a in agents}
    wk, mult = weekly_multipliers()
    weights = aw.apply(base, mult) if USE_PERF_WEIGHTS else base   # default x performance multiplier, when turned on
    weights = votes.weights(weights)                               # votes switched off by the review board (or you)
    voting_off = set(votes.off())
    labels = {a.name: a.label for a in agents}
    report = chief(ctx, results, weights, check)
    _apply_news_hook(report, results)
    try:
        track.evaluate(ctx)          # settle earlier trades first, so the coach sees today's real results
        track.sync_journal()         # finished demo trades go into the journal ("AuEdge Demo")
    except Exception as e:  # noqa: BLE001 - the track record must never break the analysis
        print(f"[track] {e}")
    try:                             # training dataset: this step with every agent's features, labels for older steps
        if ctx.futures_last is not None:
            dataset.record_step("live", None, ctx.generated_at.timestamp(), ctx.futures_last, results, report)
            fut15 = ctx.struct("15m")
            if fut15:
                await asyncio.to_thread(dataset.label, trade_review._candles(
                    [{"t": c.t, "h": c.h, "l": c.l, "c": c.c} for c in fut15.candles]))
    except Exception as e:  # noqa: BLE001 - the dataset must never break the analysis
        print(f"[dataset] {e}")
    try:                             # trade reviewer: who suggested each finished trade, why it won or lost
        fut = ctx.struct("15m")
        live = [{"t": c.t, "h": c.h, "l": c.l, "c": c.c} for c in fut.candles] if fut else None
        tr_res = await asyncio.to_thread(trade_review.run, live)
        last_rv = _review_latest()
        if (votes.state()["auto_apply"] and trade_review.due_early_review(tr_res, votes.off())
                and time.time() - (last_rv["made_at"] if last_rv else 0) > trade_review.EARLY_REVIEW_AFTER_S
                and review_run(False).get("ok")):
            trade_review.mark_early_review()   # the board backtests the weak vote; it changes only if proven better
    except Exception as e:  # noqa: BLE001 - the reviewer must never break the analysis
        print(f"[trade review] {e}")
    psych = await run_agent(PSYCH, ctx)
    apply_to_plan(report, psych)     # discipline rules can cancel a new trade before it is recorded
    report.today = today_view(report)
    agent_rows = [{**r.model_dump(), "label": labels.get(r.agent, r.agent), "weight": round(weights.get(r.agent, 0), 2),
                   "base_weight": base.get(r.agent, 0), "perf": mult.get(r.agent), "vote_off": r.agent in voting_off,
                   "perf_weight": round(aw.apply(base, mult).get(r.agent, 0), 2)} for r in results]
    agent_rows.append({**psych.model_dump(), "label": PSYCH.label, "weight": 0})
    try:
        track.record(ctx, results, report)
        record = track.stats()
    except Exception as e:  # noqa: BLE001 - the track record must never break the analysis
        print(f"[track] {e}")
        record = None
    if use_ai and not check.veto:
        ai_text = await ai_summary.write_verdict(report.model_dump(), agent_rows)
        if ai_text:
            report.verdict, report.ai_written = ai_text, True
    return {
        "ai_enabled": ai_summary.enabled(),
        "generated_at": ctx.generated_at,
        "next_in_s": ANALYSIS_EVERY_S,
        "spot": ctx.spot,
        "futures_gap": ctx.futures_gap,
        "data_errors": ctx.errors,
        "adapter_problems": adapter_problems,
        "data_check": check,
        "chief": report,
        "agents": agent_rows,
        "track": record,
        "weights_week": wk,
        "perf_weights_on": USE_PERF_WEIGHTS,
    }


@app.get("/api/analysis")
async def analysis(refresh: bool = Query(False)):
    """Returns the latest analysis; recomputes if the last scheduled run was missed, or on refresh=true."""
    _last["viewed"] = time.time()
    async with _lock:
        last_slot = time.time() + next_run_in() - ANALYSIS_EVERY_S     # most recent scheduled run time
        stale = _data_failed() and time.time() - _last["at"] >= RETRY_S
        if refresh or stale or _last["report"] is None or _last["at"] < last_slot - 5:
            await _update(True)
        rep = dict(_last["report"])
        rep["next_in_s"] = max(0, int(next_run_in()))
        if _data_failed():                       # no live data: the page asks again after the retry
            rep["next_in_s"] = min(rep["next_in_s"], max(5, int(RETRY_S - (time.time() - _last["at"])) + 5))
        return rep


# ---------------- Backtest tab: runs backtest.py as a separate process so the live dashboard stays responsive
BT_DIR = Path(__file__).parent / "data" / "backtests"
_bt: dict = {"proc": None, "id": None, "started": 0.0}


def _bt_range() -> dict:
    """Dates the cached data can test (no download): earliest start for hourly and 15m steps, and the latest day."""
    import json
    cache = Path(__file__).parent / "data" / "backtest_cache"
    def span(name):
        try:
            pts = json.loads((cache / f"{name}.json").read_text())["points"]
            return pts[0]["t"], pts[-1]["t"]
        except Exception:  # noqa: BLE001 - no cache yet
            return None, None
    h0, _ = span("fut_1h")
    m0, m1 = span("fut_15m")
    return {"first_1h": h0 + 30 * 86400 if h0 else None, "first_15m": m0 + 5 * 86400 if m0 else None,
            "last": m1, "cached": bool(h0 and m0)}


def _bt_summary(path: Path) -> dict | None:
    import json
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - half-written or broken file
        return None
    if "error" in d:
        return None
    return {"id": path.stem, "made_at": d["made_at"], **d["params"], "n": d["summary"]["n"],
            "win_rate": d["summary"]["win_rate"], "total_r": d["summary"]["total_r"],
            "total_usd": (d.get("usd") or {}).get("total_usd")}


@app.get("/api/backtest/info")
def backtest_info():
    runs = [s for s in (_bt_summary(p) for p in BT_DIR.glob("bt_*.json")) if s]
    return {"range": _bt_range(), "runs": sorted(runs, key=lambda r: -r["made_at"])[:30]}


@app.post("/api/backtest/run")
def backtest_run(start: str = Body(..., embed=True), end: str = Body(..., embed=True),
                 step: str = Body("auto", embed=True), spread: float = Body(0.30, embed=True),
                 target_rr: float | None = Body(None, embed=True), partial: bool = Body(True, embed=True),
                 account: float = Body(25000, embed=True), lot: float = Body(0.1, embed=True),
                 adaptive: bool = Body(False, embed=True), day_max_loss: float = Body(350, embed=True),
                 day_max_profit: float = Body(150, embed=True), live_rules: bool = Body(True, embed=True),
                 stop_slip: float = Body(0.0, embed=True), f_session: bool = Body(False, embed=True),
                 f_trend: bool = Body(False, embed=True), f_hunt: bool = Body(False, embed=True)):
    import re
    import subprocess
    import sys
    if _bt["proc"] and _bt["proc"].poll() is None:
        return {"ok": False, "error": "A backtest is already running. Wait for it to finish."}
    if not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", start) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end)) or start > end:
        return {"ok": False, "error": "Pick a valid period (start on or before end)."}
    if step not in ("auto", "15m", "1h") or not 0 <= spread <= 5 or not 0 <= stop_slip <= 10:
        return {"ok": False, "error": "Invalid step or cost."}
    if (target_rr is not None and not 0.5 <= target_rr <= 10) or not 100 <= account <= 1e8 or not 0.01 <= lot <= 100:
        return {"ok": False, "error": "Check the target R:R (0.5-10), account size and lot size."}
    BT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("bt_%Y%m%d_%H%M%S")
    cmd = [sys.executable, str(Path(__file__).parent / "backtest.py"), "--start", start, "--end", end,
           "--spread", str(spread), "--json-out", str(BT_DIR / f"{run_id}.json"),
           "--progress-file", str(BT_DIR / f"{run_id}.progress")]
    cmd += ["--auto"] if step == "auto" else ["--step", step]
    cmd += ["--account", str(account), "--lot", str(lot)] + (["--target-rr", str(target_rr)] if target_rr else [])
    cmd += [] if partial else ["--no-partial"]
    cmd += ["--perf-weights"] if adaptive else []
    cmd += ["--day-max-loss", str(max(0.0, day_max_loss)), "--day-max-profit", str(max(0.0, day_max_profit))]
    cmd += ([] if live_rules else ["--no-live-rules"]) + (["--stop-slip", str(stop_slip)] if stop_slip else [])
    cmd += (["--only-session"] if f_session else []) + (["--only-trend"] if f_trend else []) + (["--only-hunt"] if f_hunt else [])
    _bt.update(proc=subprocess.Popen(cmd, cwd=Path(__file__).parent, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL), id=run_id, started=time.time())
    return {"ok": True, "id": run_id}


@app.get("/api/backtest/status")
def backtest_status():
    import json
    if not _bt["id"]:
        return {"running": False}
    running = _bt["proc"].poll() is None
    prog = {}
    try:
        prog = json.loads((BT_DIR / f"{_bt['id']}.progress").read_text())
    except Exception:  # noqa: BLE001 - not written yet
        pass
    out = {"running": running, "id": _bt["id"], "elapsed": int(time.time() - _bt["started"]), "progress": prog}
    if not running:
        try:
            d = json.loads((BT_DIR / f"{_bt['id']}.json").read_text(encoding="utf-8"))
            out["error"] = d.get("error")
        except Exception:  # noqa: BLE001
            out["error"] = "The backtest stopped without a result."
    return out


@app.get("/api/backtest/result/{run_id}")
def backtest_result(run_id: str):
    import json
    import re
    if not re.fullmatch(r"(bt|hc|rv)_\d{8}_\d{6}", run_id):
        return {"error": "Unknown run."}
    try:
        return json.loads((BT_DIR / f"{run_id}.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"error": "Result not found."}


@app.post("/api/health/run")
def health_run(period: str = Body("month", embed=True)):
    """Health check: today's rules vs harsh costs, quality filters and each agent left out (backtest.py --health-check)."""
    import subprocess
    import sys
    if _bt["proc"] and _bt["proc"].poll() is None:
        return {"ok": False, "error": "A backtest is already running. Wait for it to finish."}
    rng = _bt_range()
    if not rng["cached"]:
        return {"ok": False, "error": "No downloaded history yet. Run a backtest once first."}
    day = lambda t: time.strftime("%Y-%m-%d", time.gmtime(t))          # noqa: E731
    last = rng["last"]
    start, step = (max(rng["first_1h"], last - 183 * 86400), "1h") if period == "6m" else (max(rng["first_15m"], last - 29 * 86400), "15m")
    BT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("hc_%Y%m%d_%H%M%S")
    cmd = [sys.executable, str(Path(__file__).parent / "backtest.py"), "--health-check", "--start", day(start),
           "--end", day(last), "--step", step, "--account", str(track.DEMO_ACCOUNT), "--lot", str(track.DEMO_LOT),
           "--json-out", str(BT_DIR / f"{run_id}.json"), "--progress-file", str(BT_DIR / f"{run_id}.progress")]
    _bt.update(proc=subprocess.Popen(cmd, cwd=Path(__file__).parent, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL), id=run_id, started=time.time())
    return {"ok": True, "id": run_id}


@app.get("/api/health/latest")
def health_latest():
    import json
    for path in sorted(BT_DIR.glob("hc_*.json"), reverse=True):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - half-written
            continue
        if "error" not in d:
            return {"id": path.stem, **d}
    return {"id": None}


# ---------------- Review board: weekly re-test of every agent's vote (backtest.py --review)
def _review_latest(include_failed: bool = False) -> dict | None:
    import json
    for path in sorted(BT_DIR.glob("rv_*.json"), reverse=True):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - half-written
            continue
        if "error" not in d or include_failed:
            return {"id": path.stem, **d}
    return None


@app.post("/api/review/run")
def review_run(dry_run: bool = Body(False, embed=True)):
    import subprocess
    import sys
    if _bt["proc"] and _bt["proc"].poll() is None:
        return {"ok": False, "error": "A backtest is already running. Wait for it to finish."}
    if not _bt_range()["cached"]:
        return {"ok": False, "error": "No downloaded history yet. Run a backtest once first."}
    BT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("rv_%Y%m%d_%H%M%S")
    cmd = [sys.executable, str(Path(__file__).parent / "backtest.py"), "--review", "--account", str(track.DEMO_ACCOUNT),
           "--lot", str(track.DEMO_LOT), "--json-out", str(BT_DIR / f"{run_id}.json"),
           "--progress-file", str(BT_DIR / f"{run_id}.progress")] + (["--dry-run"] if dry_run or not votes.state()["auto_apply"] else [])
    low = {"creationflags": subprocess.BELOW_NORMAL_PRIORITY_CLASS} if sys.platform == "win32" else {"preexec_fn": lambda: os.nice(10)}
    _bt.update(proc=subprocess.Popen(cmd, cwd=Path(__file__).parent, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, **low), id=run_id, started=time.time())
    return {"ok": True, "id": run_id}


@app.get("/api/review")
def review_info():
    last = _review_latest()
    if last:
        last = {k: last[k] for k in ("id", "made_at", "apply", "applied", "votes_before", "votes_after", "changes",
                                     "candidates", "confirm", "summary", "rules") if k in last}
    from agents import BUILT_IN
    return {"votes": votes.state(), "log": votes.log()[-12:][::-1], "last": last,
            "agents": [{"name": a.name, "label": a.label, "weight": a.weight} for a in BUILT_IN if a.votes and a.weight],
            "next_due": (last["made_at"] if last else time.time()) + REVIEW_EVERY_S}


@app.get("/api/trade_review")
def trade_review_info():
    """The trade reviewer's latest study: per-trade reviews, agent scorecard, what wins, what loses."""
    from agents import BUILT_IN
    d = trade_review.latest() or trade_review.run()
    return {**d, "labels": {a.name: a.label for a in BUILT_IN}, "voting_off": votes.off(),
            "reason_text": trade_review.REASON_TEXT, "win_text": trade_review.WIN_TEXT}


@app.post("/api/review/undo")
def review_undo():
    e = votes.undo()
    return {"ok": bool(e), "entry": e}


@app.post("/api/review/auto")
def review_auto(on: bool = Body(..., embed=True)):
    votes.set_auto_apply(on)
    return {"ok": True, **votes.state()}


@app.post("/api/review/vote")
def review_vote(agent: str = Body(..., embed=True), on: bool = Body(..., embed=True)):
    """Switch one agent's vote on or off by hand (logged as 'you', undo-able)."""
    from agents import BUILT_IN
    names = {a.name for a in BUILT_IN if a.votes and a.weight}
    if agent not in names:
        return {"ok": False, "error": "Unknown agent."}
    off = set(votes.off())
    if not on and len(names - off - {agent}) < votes.MIN_VOTERS:
        return {"ok": False, "error": f"At least {votes.MIN_VOTERS} agents must keep voting."}
    new = (off - {agent}) if on else (off | {agent})
    if new == off:
        return {"ok": True}
    votes.change(sorted(new), "you", [{"agent": agent, "action": "on" if on else "off"}], "Changed by hand")
    return {"ok": True}


@app.post("/api/review/apply")
def review_apply(run_id: str = Body(..., embed=True)):
    """Apply a suggest-only review's changes (if the votes haven't changed since it ran)."""
    last = _review_latest()
    if not last or last["id"] != run_id or not last.get("changes"):
        return {"ok": False, "error": "Only the latest review's suggestions can be applied."}
    if sorted(votes.off()) != sorted(last["votes_before"]):
        return {"ok": False, "error": "The votes changed since this review ran. Run a new review."}
    votes.change(last["votes_after"], "you (approved the review board)", last["changes"], last["summary"], run_id)
    return {"ok": True}


# ---------------- Trading journal: prop-firm accounts, phases and your trades (core/journal.py, data/journal.db)
@app.get("/api/journal/accounts")
def journal_accounts(archived: bool = False):
    from core import journal
    return {"accounts": journal.accounts(archived), "now": time.time()}


@app.post("/api/journal/accounts")
def journal_create(data: dict = Body(...)):
    from core import journal
    try:
        size = float(data.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    name = str(data.get("name") or "").strip()
    rules = journal.clean_rules(data.get("rules") or {})
    if not name or not 100 <= size <= 1e8:
        return {"ok": False, "error": "Give the account a name and a size (100 or more)."}
    if not rules["phases"] or any(p["target_pct"] is None for p in rules["phases"]):
        return {"ok": False, "error": "Every phase needs a profit target %."}
    return {"ok": True, "id": journal.create_account(name, str(data.get("firm") or ""), size, rules, str(data.get("notes") or ""))}


@app.get("/api/journal/accounts/{aid}")
def journal_account(aid: int):
    from core import journal
    return journal.account(aid) or {"error": "Account not found."}


@app.put("/api/journal/accounts/{aid}")
def journal_update(aid: int, data: dict = Body(...)):
    from core import journal
    journal.update_account(aid, str(data.get("name") or "Account"), str(data.get("firm") or ""), str(data.get("notes") or ""),
                           data.get("rules"))
    if "archived" in data:
        journal.archive_account(aid, bool(data["archived"]))
    return {"ok": True}


@app.post("/api/journal/accounts/{aid}/advance")
def journal_advance(aid: int, result: str = Body(..., embed=True), note: str = Body("", embed=True),
                    next_balance: float | None = Body(None, embed=True)):
    from core import journal
    return journal.advance(aid, result, note, next_balance)


@app.post("/api/journal/accounts/{aid}/reopen")
def journal_reopen(aid: int):
    from core import journal
    return journal.reopen_phase(aid)


@app.get("/api/journal/trades")
def journal_all_trades():
    """All records: every trade in every account (newest first)."""
    from core import journal
    return {"trades": journal.all_trades()}


@app.post("/api/journal/trades")
def journal_add_trade(data: dict = Body(...)):
    from core import journal
    return journal.save_trade(data)


@app.put("/api/journal/trades/{tid}")
def journal_edit_trade(tid: int, data: dict = Body(...)):
    from core import journal
    return journal.save_trade(data, tid)


@app.delete("/api/journal/trades/{tid}")
def journal_delete_trade(tid: int):
    from core import journal
    journal.delete_trade(tid)
    return {"ok": True}


@app.get("/api/journal/file/{name}")
def journal_file(name: str):
    from core import journal
    from fastapi import HTTPException
    f = journal.image_path(name)
    if not f:
        raise HTTPException(status_code=404)
    return FileResponse(f)


@app.get("/api/news")
def news_tab():
    """Gold-relevant news for the News tab: this week's ForexFactory USD events and the next official releases."""
    from core import news
    news.refresh_feed()
    now = time.time()
    rows = []
    for e in news.week_feed():
        a, b = news.window({"t": e["t"], "kind": "FOMC" if "FOMC" in e["name"] or "Federal Funds" in e["name"] else "FEED"})
        rows.append({**e, "blocks": e["impact"] == "High", "win_from": a, "win_to": b, "source": "ForexFactory"})
    week_slots = {x["t"] // 600 for x in rows}
    official = [{"t": e["t"], "name": e["name"], "impact": "High", "forecast": "", "previous": "", "blocks": True,
                 "win_from": news.window(e)[0], "win_to": news.window(e)[1], "source": "Official schedule"}
                for e in news.official() if now - 3600 <= e["t"] <= now + 35 * 86400 and e["t"] // 600 not in week_slots]
    blocking = news.blackout(now)
    return {"now": now, "blocking": {**blocking, "label": news.label(blocking, now)} if blocking else None,
            "events": sorted(rows + official, key=lambda x: x["t"])}


def _backup_candles(start: int, end: int, sec: int = 900) -> dict:
    """15m spot candles from the trading_research backup's 1-minute data (data/news_intel/xau_1m.npz), for replaying
    backtests that ran on that backup (2020 onwards, spot prices)."""
    import numpy as np
    f = Path(__file__).parent / "data" / "news_intel" / "xau_1m.npz"
    if not f.exists():
        return {"error": "The backup's 1-minute candles are not saved yet (data/news_intel/xau_1m.npz)."}
    with np.load(f) as z:
        t = z["t"]
        a, b = np.searchsorted(t, start), np.searchsorted(t, end, side="right")
        t, o, h, l, c = t[a:b], z["o"][a:b], z["h"][a:b], z["l"][a:b], z["c"][a:b]
    if not len(t):
        return {"error": "No backup candles for that period."}
    bucket = t // sec * sec
    keys, first = np.unique(bucket, return_index=True)
    last = np.r_[first[1:], len(t)] - 1
    rows = [{"t": int(k), "o": float(o[i]), "h": float(h[i:j + 1].max()), "l": float(l[i:j + 1].min()), "c": float(c[j])}
            for k, i, j in zip(keys, first, last)]
    return {"tf": "15m", "sec": sec, "candles": rows}


@app.get("/api/backtest/candles")
def backtest_candles(start: int, end: int, src: str = ""):
    """Candles around a backtest trade, for the replay chart: 15m when the saved 15m history covers the window,
    otherwise 1H (the same candles the backtest used). src=backup: spot candles from the trading_research backup."""
    import json
    if src == "backup" and 0 < end - start <= 10 * 86400:
        return _backup_candles(start, end)
    cache = Path(__file__).parent / "data" / "backtest_cache"
    if end <= start or end - start > 10 * 86400:
        return {"error": "Invalid window."}
    from core import data as live
    raw = live._cache.get("raw") or {}
    for name, sec in (("fut_15m", 900), ("fut_1h", 3600)):
        try:
            pts = json.loads((cache / f"{name}.json").read_text())["points"]
        except Exception:  # noqa: BLE001 - no cache
            pts = []
        live_pts = raw.get(name, {}).get("points", []) if isinstance(raw.get(name), dict) else []
        if not live_pts and end > time.time() - 6 * 3600:      # e.g. just after a restart: fetch the newest candles now
            try:
                import httpx
                iv, rg = ("15m", "5d") if sec == 900 else ("1h", "1mo")
                r = httpx.get(f"{live.API}/chart?symbol=xau&interval={iv}&range={rg}", timeout=12)
                live_pts = r.json().get("points", []) if r.status_code == 200 else []
            except Exception:  # noqa: BLE001 - fall back to the saved history
                live_pts = []
        if live_pts:                                   # add the newest candles from the live dashboard (demo trades)
            merged = {p["t"]: p for p in pts}
            merged.update({p["t"]: p for p in live_pts})
            pts = [merged[t] for t in sorted(merged)]
        if pts and pts[0]["t"] <= start:
            rows = [{"t": p["t"], "o": p["o"], "h": p["h"], "l": p["l"], "c": p["c"]} for p in pts
                    if start <= p["t"] <= end and p["t"] % sec == 0        # whole candles only (no half-built snapshots)
                    and None not in (p.get("o"), p.get("h"), p.get("l"), p.get("c"))]
            return {"tf": "15m" if sec == 900 else "1h", "sec": sec, "candles": rows}
    return {"error": "No saved candles for that period."}


def _spot_now() -> float | None:
    rep = _last.get("report") or {}
    spot = rep.get("spot")
    return getattr(spot, "price", None) if spot is not None else None


@app.get("/api/demo")
async def demo():
    """Demo account: AuEdge's own demo positions (no broker), with live profit/loss on the open one.
    P&L uses the live spot price (not the last 15-min analysis); falls back to the analysis price."""
    price = await live_spot() or _spot_now()
    return {**track.demo_state(price), "journal_account": track.demo_journal_id()}


@app.get("/api/calls")
def calls(days: int = 7):
    """Trade calls of the last `days` days for the chart: live demo trades plus the newest saved backtest's trades.
    Backtest trades are in gold-futures prices; demo trades in spot prices with their `gap` (futures minus spot)."""
    import json
    since = time.time() - max(1, min(days, 30)) * 86400
    out = []
    out += [t for t in _demo_as_calls() if t["entry_t"] >= since]       # demo trades in spot prices (+ their gap)
    runs = sorted(BT_DIR.glob("bt_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if DEMO_MONTH.exists() and (BT_DIR / f"{DEMO_MONTH.read_text().strip()}.json").exists():
        runs.insert(0, BT_DIR / f"{DEMO_MONTH.read_text().strip()}.json")     # prefer the Demo tab's month run
    for path in runs:
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if "error" in d or d["params"]["end"] < since:
            continue
        for t in d["trades"]:
            if t["entry_t"] >= since:
                out.append({**t, "source": "backtest", "run": path.stem, "open": False})
        break
    return {"days": days, "calls": sorted(out, key=lambda x: x["entry_t"])}


# ---------------- Demo "last month": today's rules replayed over the last month of real candles (simulated)
DEMO_MONTH = Path(__file__).parent / "data" / "demo_month.txt"


@app.post("/api/demo/month/run")
def demo_month_run():
    """Run the last ~30 days (15m steps, $25,000, 0.1 lot, daily -$350/+$150, news filter) for the Demo tab."""
    from datetime import datetime, timezone
    rng = _bt_range()
    if not rng.get("cached"):
        return {"ok": False, "error": "No downloaded history yet. Run a backtest once first."}
    last = rng["last"]
    start = max(rng["first_15m"], last - 30 * 86400)
    day = lambda ts: datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
    r = backtest_run(start=day(start), end=day(last), step="15m", spread=0.30, target_rr=None, partial=True,
                     account=track.DEMO_ACCOUNT, lot=track.DEMO_LOT, adaptive=False, day_max_loss=350, day_max_profit=150,
                     live_rules=True, stop_slip=0.0, f_session=False, f_trend=False, f_hunt=False)
    if r.get("ok"):
        DEMO_MONTH.write_text(r["id"])
    return r


@app.get("/api/demo/month")
def demo_month():
    """The last-month simulation shown in the Demo tab (or its progress while it runs)."""
    import json
    if not DEMO_MONTH.exists():
        return {"status": "none"}
    run_id = DEMO_MONTH.read_text().strip()
    if _bt["id"] == run_id and _bt["proc"] and _bt["proc"].poll() is None:
        return {"status": "running", "id": run_id, **backtest_status()}
    try:
        d = json.loads((BT_DIR / f"{run_id}.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"status": "none"}
    return {"status": "error", "error": d["error"]} if "error" in d else {"status": "done", "id": run_id, "result": d}


# ---------------- Calendar: everything AuEdge did on a given day (live data first, else the simulated month)
def _demo_as_calls() -> list[dict]:
    """Live demo trades in the replay format, in SPOT prices like the Demo tab. `gap` (futures minus spot at entry) lets
    the replay charts shift their futures candles to spot."""
    st = track.demo_state(_spot_now())
    out = []
    for t in st["closed"] + st["open"]:
        g = t["gap"] or 0
        out.append({"source": "demo", "side": t["side"], "kind": "now", "decided_t": int(t["ts"]), "entry_t": int(t["ts"]),
                    "exit_t": int(t["closed_ts"]) if t["closed_ts"] else None, "entry": t["entry"], "stop": t["stop"],
                    "t1": t["t1"], "exit": t["exit_price"], "gap": g, "half": bool(t.get("half")),
                    "r": t["result_r"] if t["result_r"] is not None else 0.0,
                    "usd": t.get("usd") if t["status"] != "open" else t.get("unrealised"),
                    "why": t.get("why") or t["status"], "open": t["status"] == "open"})
    return out


def _calendar_sources() -> dict:
    """Live snapshots and outcomes from track.db, plus the simulated month (steps + trades)."""
    import json
    with track._db() as con:
        live_steps = [json.loads(s) for (s,) in con.execute("SELECT snap FROM recs WHERE snap IS NOT NULL ORDER BY ts")]
        live_calls = con.execute("SELECT agent, ts, outcome FROM calls WHERE agent != 'chief'").fetchall()
    sim = {}
    if DEMO_MONTH.exists():
        try:
            sim = json.loads((BT_DIR / f"{DEMO_MONTH.read_text().strip()}.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            sim = {}
    return {"live_steps": live_steps, "live_calls": live_calls, "live_trades": _demo_as_calls(),
            "sim_steps": sim.get("steps", []), "sim_trades": [{**t, "source": "simulated"} for t in sim.get("trades", [])]}


def _day_of(ts: float, tz: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts - tz * 60, timezone.utc).strftime("%Y-%m-%d")


@app.get("/api/calendar")
def calendar(tz: int = 0):
    """Per local day: demo profit/loss, trades and NOW calls; live data where it exists, otherwise simulated."""
    src = _calendar_sources()
    days: dict[str, dict] = {}
    for kind in ("live", "sim"):
        for st in src[f"{kind}_steps"]:
            d = days.setdefault(_day_of(st["t"], tz), {"pnl": 0.0, "trades": 0, "nows": 0, "live": False, "sim": False})
            d[kind] = True
            d["nows"] += st["k"] == "now"
    for kind in ("live", "sim"):
        for t in src[f"{kind}_trades"]:
            if not t.get("exit_t") or t.get("open"):
                continue
            k = _day_of(t["exit_t"], tz)
            d = days.setdefault(k, {"pnl": 0.0, "trades": 0, "nows": 0, "live": False, "sim": False})
            if kind == "sim" and d["live"]:
                continue                                   # a day with live data shows only live results
            d["pnl"] += t.get("usd") or 0.0
            d["trades"] += 1
            d[kind] = True
    for d in days.values():
        d["pnl"] = round(d["pnl"], 2)
    return {"days": days}


@app.get("/api/calendar/day")
def calendar_day(date: str, tz: int = 0):
    """Everything for one local date: Chief call timeline, agents' results, levels, demo trades, replay window."""
    from datetime import datetime, timezone
    import re
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or not -900 <= tz <= 900:
        return {"error": "Pick a valid date."}
    src = _calendar_sources()
    live = [s for s in src["live_steps"] if _day_of(s["t"], tz) == date]
    kind = "live" if live else "sim"
    steps = live or [s for s in src["sim_steps"] if _day_of(s["t"], tz) == date]
    trades = [t for t in src[f"{kind}_trades"]
              if _day_of(t["entry_t"], tz) == date or (t.get("exit_t") and _day_of(t["exit_t"], tz) == date)]
    agents: dict[str, dict] = {}
    if kind == "live":
        for agent, ts, outcome in src["live_calls"]:
            if _day_of(ts, tz) == date:
                a = agents.setdefault(agent, {"calls": 0, "hit": 0, "miss": 0, "flat": 0, "pending": 0})
                a["calls"] += 1
                a[outcome if outcome in ("hit", "miss", "flat") else "pending"] += 1
    else:
        for st in steps:
            for name, bias, _conf, outcome in st["ag"]:
                if bias in ("BUY", "SELL"):
                    a = agents.setdefault(name, {"calls": 0, "hit": 0, "miss": 0, "flat": 0, "pending": 0})
                    a["calls"] += 1
                    a[outcome if outcome in ("hit", "miss", "flat") else "pending"] += 1
    timeline, last = [], None                              # only the moments the Chief's answer changed
    for st in steps:
        key = (st["a"], st["sd"])
        if key != last:
            timeline.append({k: st[k] for k in ("t", "p", "a", "k", "sd", "cf", "tr", "lv")})
            last = key
    day0 = int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()) + tz * 60
    return {"date": date, "source": kind, "steps": len(steps), "nows": sum(s["k"] == "now" for s in steps),
            "timeline": timeline, "agents": agents, "trades": sorted(trades, key=lambda t: t["entry_t"]),
            "levels": {"start": steps[0] if steps else None, "end": steps[-1] if steps else None},
            "window": [day0, day0 + 86400], "pnl": round(sum(t.get("usd") or 0 for t in trades
                                                            if t.get("exit_t") and not t.get("open")
                                                            and _day_of(t["exit_t"], tz) == date), 2)}
