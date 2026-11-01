# News Intelligence Integration (sub-project 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the news layer into the live app and the backtest: expected volatility, AVOID gates and explanations always on; the direction view shown as advisory next to the Chief's call, able to act only in `live` mode.

**Architecture:** A one-off export (`python -m core.newsintel.ml --export`) fits the models on all history and writes artifacts to `data/news_intel/models/`. A pure inference module (`core/newsintel/live.py`) turns the current market context + calendar into an `Intel` object. A non-voting `news_intel` agent shows it; a small Chief hook adds explanations (and, only in `live` mode, adjusts confidence); a gates module adds AVOID blocks to the Discipline coach and the backtest. The React pages show it from the agent's `extra` field.

**Tech Stack:** Python 3 / FastAPI / pydantic, numpy, scikit-learn (already a dependency), pytest; React (web/) for the cards.

**Spec:** `docs/superpowers/specs/2026-10-31-news-intelligence-design.md` §7 (with the 2026-11-01 clarification) and §2 decisions.

## Global Constraints

- `NEWSINTEL_MODE = off | advisory | live`, read from the environment, default `advisory`. Unknown values → `advisory`.
- `live` may only take effect when the exported artifact's `go_live` is true (recorded from the harness verdict). If `NEWSINTEL_MODE=live` but `go_live` is false, behave as `advisory` and say so in the agent's warnings.
- Volatility expectation, AVOID gates and explanations are on in `advisory` and `live`; `off` disables all of it.
- With `NEWSINTEL_MODE=off` the Chief report and the backtest output must be identical to today's.
- The news layer never creates a trade, never changes agent weights or Discipline limits. Outputs stay BUY / SELL / WAIT; AVOID shows as a Discipline block.
- `live` may lower confidence, turn BUY/SELL into WAIT when P(side of the call) < `WEAK_P = 0.40`, and raise confidence only up to `MAX_CONFIDENCE` (85, `agents/chief.py`).
- Event window: 24 h before an event = "pre"; from release to release + 180 min = "post"; otherwise "none".
- Blackout: 30 min before / 30 min after every calendar event; FOMC keeps 60 min after (`core/news.py` constants).
- Abnormal volatility: current M5 range / M5 ATR(14) above the 99th percentile of non-event history (threshold fitted at export).
- Spread expansion: spread > 3 × median spread, live only (backtest has no historical spread).
- The expected move is shown as "typical first-hour move for this kind of release" — the sub-project 2 final review found it is essentially ATR scaling (no measurable edge from the news buckets), so no UI text may call it a news forecast or claim it beats anything.
- `go_live` comes from the harness's go-live check, which (after the sub-project 2 fix wave) requires both the i.i.d. and the block-bootstrap CI upper bounds < 0.
- Plain-language text for the user (a trader): no jargon like "log-loss" in UI strings; use "chance", "expected move", "similar past releases".
- Never kill processes you did not start; never restart the :8000 server. Commit with explicit `git add <paths>` only.
- Files with the user's uncommitted edits (`app.py`, `backtest.py`, `agents/__init__.py`, `static/*`, `core/data.py`, `core/journal.py`): see Task 0.

## Review Focus

1. No FRED key / FRED down / release not yet on FRED after release → "post" phase with surprise unknown (z missing), never an exception. Test in Task 2.
2. Live candles missing or short (weekend, market closed, futures feed gap) → `Intel` with phase computed but expected move `None` and a plain note; agent returns OK with "no news context", not ERROR. Test in Task 2/3.
3. Artifacts missing (export never run) → agent says "News models not built yet (run python -m core.newsintel.ml --export)"; gates fall back to calendar blackout only; Chief unchanged. Test in Task 3/5.
4. Two events close together (e.g. CPI + claims same 08:30, FOMC day) → one `Intel` built for the highest-priority kind (`PRIORITY` in `ml/data.py`), the others listed by name. Test in Task 2.
5. ForexFactory titles that don't map to a known kind → still block (blackout) but give no forecast. Test in Task 2.

---

### Task 0: Get the user's pending edits out of the way (controller, no subagent)

The user's uncommitted edits to `app.py`, `backtest.py`, `agents/__init__.py` must not be committed by us. Before Task 3, the controller asks the user (once) to either commit those edits themselves, or allow a commit of them as-is titled `chore: user's pending edits (ICT agent, backup replay, webapp route)`. If the user declines both, Tasks 3, 4 and 5 leave their hooks in those three files **uncommitted** and say so in the report; their new modules and tests are still committed.

### Task 1: Export model artifacts

**Files:**
- Create: `core/newsintel/ml/export.py`
- Modify: `core/newsintel/ml/__main__.py` (add `--export`)
- Test: `tests/newsintel/ml/test_export.py`

**Interfaces:**
- Consumes: `ml.data.load()`, `ml.harness.run(ds, label)` (its `Results` for `go_live`, primary choice), `ml.models` classes + `tune`, `ml.stack.Stacker`, `ml.metrics.fit_temperature`, `ml.stats.describe`, `core/newsintel/minutes.load_backup_minutes` cache `data/news_intel/xau_1m.npz`.
- Produces: `MODELS_DIR = DATA / "news_intel" / "models"`; `export(ds, out=MODELS_DIR) -> dict` (the meta dict) writing `models.pkl` and `meta.json`; `load_artifacts(path=MODELS_DIR) -> Artifacts | None`.
  `Artifacts` (dataclass): `primary` (fitted news model), `primary_name: str`, `stacker` (fitted `Stacker`), `technical` (fitted `TechnicalOnly`), `temperature: float`, `vol_table: dict[tuple[str, bool], float]` (median |move60|/atr15 per (kind, |z|>=1)), `vol_kind: dict[str, float]`, `vol_overall: float`, `stats_rows: list[dict]` (`stats.describe` over all rows), `neighbours_X` / `neighbours_meta` (scaled X, plus t, kind, z, move60 per row for the similar-releases lookup), `uncertain_max_p: float`, `uncertain_bhatt: float`, `m5_range_p99: float`, `go_live: bool`, `trained_through: str` (YYYY-MM-DD of last row), `version: str` (UTC timestamp).

- [ ] **Step 1: Write failing tests** on the fixture DB already used by `tests/newsintel/ml` (reuse its conftest helpers):
  - `test_export_roundtrip`: `export` then `load_artifacts` returns an `Artifacts` whose `stacker` predicts rows summing to 1 and whose `go_live` equals the harness verdict.
  - `test_vol_table_matches_harness_rule`: for a (kind, big) bucket with ≥ 5 rows the stored median equals `np.median(absmove60/atr15)` of those rows; a bucket with < 5 falls back to kind, then overall (same rule as `stack.vol_forecast`).
  - `test_primary_choice_uses_all_folds`: primary = the candidate with lowest pooled OOS log-loss over all folds (Bayes/KNN/LogReg, Forest only if it beats LogReg with 95 % CI below 0) — this is the forward choice for unseen future rows, not a look-ahead.
  - `test_thresholds`: `uncertain_max_p` = 20th percentile of the stacker's max class probability over the harness OOS rows; `uncertain_bhatt` = 80th percentile of the neighbour Bhattacharyya distance over OOS rows; `m5_range_p99` = 99th percentile of (5-minute range / 14-bar ATR of 5-minute bars) over 1-minute history outside every event window (30 min before to 180 min after).
  - `test_load_missing_returns_none`.
- [ ] **Step 2:** run `.venv\Scripts\python.exe -m pytest tests/newsintel/ml/test_export.py -q` → FAIL.
- [ ] **Step 3:** implement. Fit everything on all rows (label60). Pickle with `pickle` (protocol 5); `meta.json` holds the scalar fields + `go_live`, `primary_name`, `trained_through`, `version`. `__main__` `--export` runs the harness (label60), exports, prints one line `Exported news models (trained through D, primary P, go-live yes/no) to PATH`.
- [ ] **Step 4:** tests PASS; run the real export once and paste the printed line into the report.
- [ ] **Step 5:** commit `core/newsintel/ml/export.py core/newsintel/ml/__main__.py tests/newsintel/ml/test_export.py` (artifacts in `data/` are not committed). Message `feat(newsintel): export fitted models and thresholds`.

### Task 2: Live inference (`Intel`)

**Files:**
- Create: `core/newsintel/live.py`
- Test: `tests/newsintel/test_live.py`

**Interfaces:**
- Consumes: `Artifacts` (Task 1), `core.news.events()` (official CPI/NFP/FOMC + ForexFactory high-impact USD), `core.newsintel.calendar.RELEASES`, `fred.fetch_vintages`/`first_releases`, `surprise.expectations`, `ml.data.FEATURE_NAMES`, `ml.stats.bhattacharyya`, `core.indicators.atr`, `core.structure.tf_bias`, `agents.chief.TFS`.
- Produces:
  - `kind_of(name: str) -> str | None` — maps official kinds and ForexFactory titles: "CPI"→CPI, "Core PCE"/"PCE"→PCE, "PPI"→PPI, "Non-Farm"/"NFP"→NFP, "GDP" (advance only)→GDP, "Retail Sales"→RETAIL, "Unemployment Claims"→CLAIMS, "FOMC"/"Federal Funds Rate"→FOMC; else None.
  - `@dataclass Intel`: `phase: str` ("pre"|"post"|"none"), `event: dict | None` ({kind, name, t}), `others: list[str]`, `expected_move: float | None` (dollars, 60 min after release), `expected_range: tuple[float, float] | None` (price ± expected_move), `probs: dict[str, float] | None` (down/side/up, stacker, temperature-scaled), `tech_probs: dict | None`, `surprise_z: float | None`, `similar: list[dict]` (≤ 8: date, kind, z, move60, label), `coherence: float | None` (Bhattacharyya distance), `uncertain: bool`, `notes: list[str]`, `go_live: bool`, `trained_through: str | None`.
  - `build_intel(ctx: MarketContext, now: float, art: Artifacts | None, fetch=True) -> Intel`.
  - `live_features(ctx, t: int, prev_t: int | None, z: float | None, core_z: float | None, kind: str) -> np.ndarray` — one row in `FEATURE_NAMES` order, computed from `ctx.struct("15m"/"1h"/"4h"/"1d")` and the 5m/1m candles of the last 60 min before t (spot preferred, futures shifted by `ctx.futures_gap`), same definitions as `core/newsintel/features.py`.
- [ ] **Step 1: failing tests** (synthetic ctx built from fixture candles, a fake `Artifacts` with known numbers):
  - `test_phase_windows`: 23 h before → pre; release+179 min → post; 25 h before → none.
  - `test_priority_and_others` (Review Focus 4): CPI and CLAIMS at the same 08:30 → event CPI, others ["Jobless Claims"].
  - `test_unknown_feed_title` (5): kind None → phase none for forecasting, title kept in notes.
  - `test_no_fred` (1): `fetch` raising → post phase, `surprise_z` None, z_missing=1 in the row, note "Actual not published yet".
  - `test_short_candles` (2): fewer than 60 15m candles → `expected_move` None, `probs` None, note, no exception.
  - `test_expected_move`: equals `vol_table[(kind, |z|>=1)] × atr15`.
  - `test_uncertain_flag`: max prob below `uncertain_max_p` or coherence above `uncertain_bhatt` → `uncertain` True.
  - `test_feature_parity`: on fixture 1-minute data, `live_features` built from resampled candles equals `features.features()` for the same t within 1e-6 (atr15, atr1h, pre_range/atr15, trend_score).
- [ ] **Step 2:** FAIL. **Step 3:** implement (pre phase: surprise unknown → z_missing; post: fetch first release of that day for the kind's headline series, compute z with `expectations` on the full vintage history; FRED errors caught). **Step 4:** PASS (`pytest tests/newsintel/test_live.py -q`).
- [ ] **Step 5:** commit `core/newsintel/live.py tests/newsintel/test_live.py` — `feat(newsintel): live intel from market context and calendar`.

### Task 3: `news_intel` agent

**Files:**
- Create: `agents/news_intel.py`
- Modify: `core/models.py` (`AgentResult.extra: dict = {}`), `agents/__init__.py` (add `NewsIntelAgent()` to `BUILT_IN` before `SkepticAgent()`), `core/env.py` or new `core/newsintel/mode.py` with `mode() -> str` and `effective_mode(art) -> str`
- Test: `tests/newsintel/test_agent.py`

**Interfaces:**
- Consumes: `build_intel`, `load_artifacts` (cached in-process; reload when `meta.json` mtime changes).
- Produces: `NewsIntelAgent(BaseAgent)` with `name="news_intel"`, `label="News intelligence"`, `weight=0`, `votes=False`; result `bias="WAIT"`, `bias_label` = "AVOID" if a gate in the window fired else the phase word ("BEFORE CPI", "AFTER NFP", "NO NEWS"), `rows` (expected move, chances up/side/down, surprise, model trust), `summary` (plain paragraph), `extra = dataclasses.asdict(intel) | {"mode": effective_mode}`. In `off` mode: `status="OK"`, headline "News intelligence is off", empty extra.
- [ ] **Step 1: failing tests:** artifacts missing (Review Focus 3) → OK result with the "not built yet" warning; `off` mode → empty extra; `live` requested with `go_live` False → extra.mode == "advisory" and a warning; Chief voters ignore it (run `agents.chief.chief` with and without the agent result in `results` → identical bias/confidence).
- [ ] **Step 2–4:** FAIL → implement → PASS (`pytest tests/newsintel/test_agent.py -q`), plus `python tools/smoke_test.py` still passes.
- [ ] **Step 5:** commit new files + `core/models.py`; `agents/__init__.py` per Task 0. `feat(agents): advisory news intelligence agent`.

### Task 4: Chief explanations and the mode switch

**Files:**
- Create: `core/newsintel/chief_hook.py`
- Modify: `app.py` (after `report = chief(...)`, call `apply_news(report, news_result)`), `backtest.py` (same after its `chief(...)`, using a backtest-safe intel without FRED fetch: `fetch=False`, surprise from `news_intel.db` events)
- Test: `tests/newsintel/test_chief_hook.py`

**Interfaces:**
- Produces: `apply_news(rep: ChiefReport, news: AgentResult | None) -> None`. advisory: append to `rep.reasons` one line "News (advisory): before CPI expect about $X in the first hour (range A–B); chances up U % / flat S % / down D %; N similar past releases moved …" and nothing else. live (effective): additionally if the call is BUY/SELL and P(that side) < `WEAK_P` → bias WAIT, plan kind "none" with action "WAIT (news view disagrees)"; if P(side) ≥ 0.55 → confidence + up to 5 capped at `MAX_CONFIDENCE`; if `uncertain` → confidence − 10 (floor 0). Never sets a plan where there was none.
- [ ] **Step 1: failing tests:** `test_off_identical` (mode off: report dump before == after), `test_advisory_only_adds_reason` (only `reasons` grows), `test_live_weak_side_turns_wait`, `test_live_cap`, `test_live_never_creates_trade`.
- [ ] **Step 2–4:** FAIL → implement → PASS; run a 2-day backtest with `NEWSINTEL_MODE=off` before and after the change and confirm identical trades (paste the command and the trade count).
- [ ] **Step 5:** commit new files; `app.py`/`backtest.py` per Task 0. `feat(newsintel): chief explanations and mode switch`.

### Task 5: AVOID gates

**Files:**
- Create: `core/newsintel/gates.py`
- Modify: `agents/psychology.py` (`assess(..., m5: list | None = None, spread: float | None = None, intel: dict | None = None)`), `backtest.py` (`block_reason`: call `gates.avoid` when `SETTINGS.get("news", True)`; return `"news_" + code`)
- Test: `tests/newsintel/test_gates.py`

**Interfaces:**
- Produces: `calendar_events() -> list[dict]` (union of `core.news.events()` and historical events from `news_intel.db`, deduplicated per 10-minute slot, sorted); `blackout(ts) -> dict | None` over that union with the `core.news.window` rule; `avoid(ts, m5: list[Candle] | None, spread: float | None, spread_median: float | None, intel: dict | None, art: Artifacts | None) -> tuple[str, str] | None` returning `(code, plain message)` with codes `calendar`, `volatility`, `spread`, `uncertain`, checked in that order. `uncertain` only inside an event window (pre within 2 h, or post).
- [ ] **Step 1: failing tests:** blackout covers a historical PPI time from the DB that `core.news.blackout` misses; FOMC 60 min after; abnormal volatility above `m5_range_p99` blocks, just below does not; spread 3.1× median blocks and `spread=None` never blocks; uncertainty blocks only inside the window; artifacts None → only `calendar` can fire (Review Focus 3); `assess` with no new args behaves exactly as before.
- [ ] **Step 2–4:** FAIL → implement → PASS (`pytest tests/newsintel/test_gates.py -q`, `python tools/smoke_test.py`). Re-run the saved baseline backtest period (2026-05-26 → 2026-08-14, backup data) in `advisory` and report trades / R / drawdown vs the baseline in spec §1 (61 trades, +1.08R, 12R max DD) — this is evidence for the user, not a pass/fail gate.
- [ ] **Step 5:** commit `core/newsintel/gates.py agents/psychology.py tests/newsintel/test_gates.py`; `backtest.py` per Task 0. `feat(newsintel): AVOID gates in discipline coach and backtest`.

### Task 6: M5 confirmation chips

**Files:**
- Create: `core/newsintel/m5.py`
- Modify: `agents/news_intel.py` (add `extra["m5"]`)
- Test: `tests/newsintel/test_m5.py`

**Interfaces:**
- Produces: `m5_confirmations(candles: list[Candle]) -> dict` → `{"bos": "up"|"down"|None, "retest": "up"|"down"|None, "text": str}`; BOS = `structure.last_bos` on `zigzag(candles, 2.0)` within the last 6 bars; retest = after that BOS, a bar's low (up) / high (down) touched the broken level within 0.25 × ATR and closed back beyond it.
- Ruling carried here: M5 confirmations are display-only chips in this plan. Feeding them to the stacker and making them entry requirements needs a harness re-run with new features — that belongs to sub-project 4's scheduled re-run (spec §7: "they become entry requirements only if they pass the same walk-forward check").
- [ ] **Steps 1–5:** synthetic candles with a clear break up / break down / none / break-and-retest → tests FAIL → implement → PASS → commit `core/newsintel/m5.py agents/news_intel.py tests/newsintel/test_m5.py` — `feat(newsintel): m5 break and retest chips`.

### Task 7: Cards in the React app

Runs after UI-rebuild Tasks 8 (News) and 11 (Agents + Trade) exist.

**Files:**
- Create: `web/src/components/NewsIntelCard.tsx`
- Modify: the News page, Trade page and Agents page components created by the UI plan (paths from that plan's ledger)

**Interfaces:**
- Consumes: the analysis API's agent row for `news_intel` (`extra` as in Task 3).
- Produces: `NewsIntelCard({extra, compact})`: event + phase, expected move and range, chances bar (up/flat/down) labelled "advisory — not used for trades" unless `extra.mode === "live"`, AVOID badge, similar past releases table (date, kind, surprise, move after 60 min), M5 chips. News page: full card; Trade page: compact (expected move + advisory chances); Agents page: the card in the agents grid.
- [ ] **Steps:** component test (vitest, as the UI plan does) for the three states (no news, pre, post with similar releases) → implement → `npm run build` in `web/` → check in the browser at http://127.0.0.1:8000/app/ → commit the web files and `static/app` build output the UI plan commits.
