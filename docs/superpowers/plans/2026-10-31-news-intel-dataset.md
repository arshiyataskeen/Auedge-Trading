# News Intelligence — Sub-project 1: Event & Reaction Dataset — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `data/news_intel.db`: every high-impact US release 2020 → now with first-release actuals and a no-lookahead surprise proxy, gold's measured 1-minute reaction to each release time, and pre-event features — from the user's `trading_research` backup and FRED/ALFRED.

**Architecture:** New package `core/newsintel/` with one file per responsibility (backup loading, bar helpers, FRED vintages, surprise, calendar, reactions, features, store, build CLI). Pure functions over numpy arrays; SQLite store in the style of `core/journal.py`. Nothing in the running app imports it yet (that is sub-project 3).

**Tech Stack:** Python 3.12, numpy (new in `requirements.txt`), httpx (existing), sqlite3, pytest (new `requirements-dev.txt`).

**Spec:** `docs/superpowers/specs/2026-10-31-news-intelligence-design.md` (sections 4, 5, 9)

## Global Constraints

- Do not change trading rules, agent weights, the Chief, the news blackout, or anything that places orders. No app module imports `core.newsintel` in this sub-project.
- Event coverage starts 2020-01-01 (backup start); FRED history is fetched from 2014-01-01 only to warm up the surprise model.
- Release times (New York): 08:30 for CPI, PPI, PCE, Employment Situation, GDP, Retail sales, Jobless claims; 14:00 FOMC (2020-03-03 emergency 10:00, 2020-03-15 emergency 17:00).
- ISM PMI and ADP are **not** built in this plan (spec 5.1: no source approved yet).
- Surprise: `surprise_z = sign × (actual − expected) / sigma`; AR(1) on earlier first releases, expanding window, min 24 points, else `expected = last value`; positive = hawkish / strong USD.
- Price at time x = close of the last 1-minute candle with `t + 60 ≤ x`. P0 = price at T.
- Tradable label: blackout end `Tb = T + 30 min` (FOMC `T + 60 min`); label60 = move `Tb → Tb + 60 min`, label120 = `Tb → Tb + 120 min`; `"side"` if |move| < 0.5 × pre-event M15 ATR(14), else `"up"`/`"down"`.
- Incomplete: fewer than 90 % of the 240 expected 1-minute candles in `[T − 60 min, T + 180 min)` → `incomplete = 1`.
- FRED key from env `FRED_API_KEY` (loaded by `core.env.load_env()` from `.env`); downloads cached in `data/news_intel/fred/`.
- One reaction row per distinct release time `t` (several releases at the same `t` share it).

## Review Focus

- Release time with no candles (market closed, e.g. 2020-03-15 Sunday 17:00, Good Friday NFP) → reaction stored with `incomplete = 1` and null prices, no exception. *(Task 6 test `test_reaction_when_market_closed`)*
- Several releases at the same time (GDP + PCE + claims at 08:30) → one `reactions` row for that `t`, each event row points to it, nothing duplicated. *(Task 8 test `test_shared_release_time_one_reaction`)*
- Revised data: the "actual" must be the first-release value and "previous" must be the value as known on that release day, not today's revised number. *(Task 3 test `test_first_release_uses_vintage_not_revision`)*
- Daylight saving: 08:30 New York must map to 13:30 UTC in winter and 12:30 UTC in summer. *(Task 5 test `test_release_time_dst`)*
- Re-running the build (and running it offline once FRED is cached) gives identical row counts; missing key with no cache gives a clear error. *(Task 8 tests `test_build_idempotent`, Task 3 `test_missing_key_without_cache_errors`)*

---

### Task 1: Backup loader (pg_dump reader + 1-minute arrays)

**Files:**
- Create: `tools/pgdump_read.py` (from the reader used for the 2026-10-31 backtest, turned into a streaming function)
- Create: `core/newsintel/__init__.py` (docstring only), `core/newsintel/minutes.py`
- Create: `requirements-dev.txt` (`pytest`), modify `requirements.txt` (add `numpy`)
- Test: `tests/newsintel/test_minutes.py`, `tests/conftest.py` (adds repo root to `sys.path`)

**Interfaces:**
- Produces: `tools.pgdump_read.iter_copy_rows(path: str | Path, table: str) -> Iterator[list[str]]` — tab-split COPY rows of the table's TABLE DATA entry; supports PGDMP 1.14–1.16, compression none/gzip; `\N` stays the literal string `"\\N"`.
- Produces: `core.newsintel.minutes.Minutes` dataclass `(t: np.ndarray[int64], o, h, l, c: np.ndarray[float64])`, sorted by `t`, unique.
- Produces: `load_backup_minutes(backup: Path, cache: Path = DATA/"news_intel"/"xau_1m.npz") -> Minutes` — rows with `granularity == "1min"` only; uses the `.npz` cache when it is newer than the backup.

- [ ] **Step 1: Write failing tests.** In the test file add a helper `_write_dump(path, rows, gzip: bool)` that writes a minimal PGDMP 1.16 archive (header, TOC with one `TABLE DATA` entry for `public.ohlcv_xauusd` whose offset points at a data block `0x01, dumpId, chunks…, 0`). Tests:
  - `test_iter_copy_rows_plain_and_gzip`: both variants yield `[["XAUUSD","1min","2024-01-02 00:00:00+00", "2050.1","2051","2049.5","2050.7","\\N","3"], …]`.
  - `test_load_minutes_filters_and_sorts`: rows given out of order plus one `1day` row → `Minutes.t` strictly increasing, length = number of `1min` rows, `t[0] == 1704153600`.
  - `test_load_minutes_uses_cache`: second call with the dump file deleted returns equal arrays.
- [ ] **Step 2:** Run `.venv\Scripts\python.exe -m pytest tests/newsintel/test_minutes.py -v` → FAIL (modules missing).
- [ ] **Step 3:** Implement `iter_copy_rows` (header and TOC parsing as in the existing reader; stream chunks through `zlib.decompressobj`, split on `\n`, carry partial lines between chunks, stop at `\.`) and `load_backup_minutes` (`datetime.fromisoformat(ts).timestamp()`, `np.savez`).
- [ ] **Step 4:** Run the tests → PASS. Then run once on the real file and check: `python -c "from core.newsintel.minutes import load_backup_minutes as L; from pathlib import Path; m=L(Path(r'C:\Users\mpm\Downloads\trading_research_xauusd_2276 (1).backup')); print(len(m.t))"` → `2347685`.
- [ ] **Step 5:** Commit `feat(newsintel): stream XAUUSD 1-minute candles from the pg_dump backup`.

### Task 2: Bar helpers

**Files:** Create `core/newsintel/bars.py`; Test `tests/newsintel/test_bars.py`

**Interfaces:**
- Consumes: `Minutes` (Task 1), `core.models.Candle`.
- Produces:
  - `price_at(m: Minutes, x: int) -> float | None` — close of last candle with `t + 60 ≤ x`; None if that candle is older than 30 min before `x` (stale).
  - `window(m: Minutes, a: int, b: int) -> slice` — candles with `a ≤ t < b`.
  - `resample(m: Minutes, sec: int, end: int, n: int, offset: int = 0) -> list[Candle]` — the last `n` finished candles of `sec` seconds ending at or before `end`, buckets `(t − offset) // sec`; `offset` lets daily candles start at 18:00 New York (pass `offset` computed per DST by the caller as `session_offset(t)`).
  - `session_day_candles(m: Minutes, end: int, n: int) -> list[Candle]` — daily candles by gold session (18:00 → 17:00 NY, named by end day), built with `zoneinfo`, only sessions finished before `end`.

- [ ] **Step 1: Failing tests:** `test_price_at_uses_finished_candle` (candles at 0,60,120; `price_at(m,120)` = close of candle t=60); `test_price_at_stale_is_none` (gap > 30 min → None); `test_resample_15m_ohlc` (30 synthetic minutes → two 15m candles with correct o/h/l/c, the forming one excluded); `test_session_day_split_at_18_ny` (a minute at 17:59 NY and one at 18:00 NY land in different days).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement with `np.searchsorted` on `m.t`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(newsintel): bar helpers (price at time, windows, resampling)`.

### Task 3: FRED/ALFRED first releases

**Files:** Create `core/newsintel/fred.py`; Test `tests/newsintel/test_fred.py`, fixture `tests/newsintel/fixtures/alfred_payems.json`

**Interfaces:**
- Produces: `fetch_vintages(series: str, offline: bool = False) -> list[dict]` — rows `{date, realtime_start, realtime_end, value}` from `https://api.stlouisfed.org/fred/series/observations?series_id=…&realtime_start=2014-01-01&realtime_end=9999-12-31&observation_start=2014-01-01&file_type=json`; cached to `data/news_intel/fred/<series>.json`; uses the cache when `offline` or when it is < 24 h old; raises `RuntimeError("FRED_API_KEY is not set and there is no cached copy of <series>")` when neither works. Values `"."` are skipped.
- Produces: `first_releases(rows: list[dict], transform: str) -> list[Release]`, `Release` dataclass `(obs_date: str, release_date: str, actual: float, previous: float | None)`; `transform` ∈ `"pct_mom"`, `"diff"`, `"level"`, `"saar_qoq"`. For each observation date, the release date is its earliest `realtime_start`; `actual` and `previous` are computed from the snapshot valid on that release date (`realtime_start ≤ V ≤ realtime_end`) of that date and the prior observation; `previous` = the prior first-release `actual`. Sorted by `release_date`.

- [ ] **Step 1: Failing tests** (fixture: hand-written PAYEMS rows where 2024-01 is first published 2024-02-02 as 157,500 with Dec at 157,147, then revised on 2024-03-08 to 157,800 / Dec 157,200):
  - `test_first_release_uses_vintage_not_revision`: `first_releases(rows,"diff")` entry for `2024-01-01` has `release_date == "2024-02-02"`, `actual == 353.0`.
  - `test_pct_mom_and_saar`: synthetic levels 100 → 100.3 gives `pct_mom` 0.3 (±1e-9); quarterly 100 → 101 gives `saar_qoq` ≈ 4.06.
  - `test_missing_key_without_cache_errors`: env without `FRED_API_KEY`, empty cache dir (monkeypatch `CACHE`) → `RuntimeError` with that message.
  - `test_offline_reads_cache`: fixture copied into cache → `fetch_vintages("PAYEMS", offline=True)` returns its rows, no network (monkeypatch `httpx.get` to raise).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement (call `core.env.load_env()` before reading the key; atomic write via `.tmp` + `replace`, as in `backtest.load_data`).
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(newsintel): first-release values from ALFRED vintages`.

### Task 4: Surprise proxy

**Files:** Create `core/newsintel/surprise.py`; Test `tests/newsintel/test_surprise.py`

**Interfaces:**
- Consumes: `Release` (Task 3).
- Produces: `expectations(releases: list[Release], sign: int, min_ar: int = 24) -> list[Surprise]`, `Surprise` dataclass `(release_date: str, expected: float | None, sigma: float | None, z: float | None)`, same order as input. For release i: history = actuals of releases 0..i−1 only. If len ≥ `min_ar`: OLS `y_t = a + b·y_{t−1}` on history, `expected = a + b·history[-1]`, `sigma = std(residuals, ddof=2)`. Else if len ≥ 3: `expected = history[-1]`, `sigma = std(diff(history), ddof=1)`. Else all None. `z = sign·(actual − expected)/sigma`, None if sigma is None or 0.

- [ ] **Step 1: Failing tests:** `test_no_lookahead` (changing release i+1's actual does not change Surprise i); `test_ar1_on_known_series` (y = 1 + 0.5·y_prev + small fixed noise → expected for the last point within 0.05 of 1 + 0.5·y_prev); `test_sign_orientation` (sign = −1 flips z); `test_short_history_fallback` (5 points → expected = previous actual).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement with `numpy.linalg.lstsq`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(newsintel): no-lookahead AR(1) surprise proxy`.

### Task 5: Event calendar

**Files:** Create `core/newsintel/calendar.py`; Test `tests/newsintel/test_calendar.py`

**Interfaces:**
- Consumes: `fetch_vintages`, `first_releases` (Task 3), `expectations` (Task 4), `core.news.FOMC` (existing list, 2025+).
- Produces:
  - `RELEASES: dict[str, dict]` — kind → `{"name", "time": (h, m), "series": [(series_id, transform, sign, headline: bool), …]}` with exactly:
    `CPI`: CPIAUCSL pct_mom +1 headline, CPILFESL pct_mom +1 · `PPI`: PPIFIS pct_mom +1 · `PCE`: PCEPI pct_mom +1 headline, PCEPILFE pct_mom +1 · `NFP`: PAYEMS diff +1 headline, UNRATE level −1 · `GDP`: GDP saar_qoq +1 (advance only = first release of each quarter) · `RETAIL`: RSAFS pct_mom +1 · `CLAIMS`: ICSA level −1. All at (8, 30).
  - `FOMC_HIST: list[tuple[str, int, int]]` — 2020-01-29, 2020-03-03 (10:00), 2020-03-15 (17:00), 2020-04-29, 2020-06-10, 2020-07-29, 2020-09-16, 2020-11-05, 2020-12-16; 2021-01-27, 03-17, 04-28, 06-16, 07-28, 09-22, 11-03, 12-15; 2022-01-26, 03-16, 05-04, 06-15, 07-27, 09-21, 11-02, 12-14; 2023-02-01, 03-22, 05-03, 06-14, 07-26, 09-20, 11-01, 12-13; 2024-01-31, 03-20, 05-01, 06-12, 07-31, 09-18, 11-07, 12-18 (14:00 unless stated); plus `core.news.FOMC` dates at 14:00.
  - `release_ts(day: str, h: int, m: int) -> int` — New York wall time → unix seconds.
  - `Component` dataclass `(series, actual, previous, expected, sigma, surprise_z, headline)`; `Event` dataclass `(kind, name, t, components: list[Component])`, `surprise_z` property = headline component's z.
  - `build_events(since: str = "2020-01-01", offline: bool = False) -> list[Event]` — components of one kind released the same day form one Event; sorted by `t`; FOMC events have no components.

- [ ] **Step 1: Failing tests:** `test_release_time_dst` (`release_ts("2024-01-11",8,30) == 1704979800`, `release_ts("2024-07-11",8,30) == 1720701000`); `test_fomc_list_complete` (40 dates 2020–2024, includes 2020-03-15 at 17:00); `test_build_events_groups_components` (monkeypatched `fetch_vintages` returning fixtures for CPIAUCSL and CPILFESL with the same release date → one `CPI` event with 2 components, headline z from CPIAUCSL); `test_events_before_since_dropped`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(newsintel): 2020+ high-impact US event calendar with surprises`.

### Task 6: Reaction measurement

**Files:** Create `core/newsintel/reactions.py`; Test `tests/newsintel/test_reactions.py`

**Interfaces:**
- Consumes: `Minutes`, `price_at`, `window`, `resample` (Tasks 1–2), `core.indicators.atr`.
- Produces: `measure(m: Minutes, t: int, blackout_after_s: int) -> Reaction`, `Reaction` dataclass with fields `t, p0, r5, r15, r30, r60, r120, max_up, max_down, vol_exp, cont, settle_min, atr15, move60, move120, label60, label120, incomplete` (USD moves; `max_up`/`max_down` = highest high − P0 and P0 − lowest low over `(T, T+120 min]`; `cont` = 1 if sign(r5) == sign(r120), 0 if opposite, None if either is 0/None; `settle_min` = first minute after T where the rolling 5-minute range ≤ 1.5 × median rolling 5-minute range of `[T−60, T)`, searched to T+180, else None; `atr15` = ATR(14) of the 15m candles finished before T; labels per Global Constraints).

- [ ] **Step 1: Failing tests** on synthetic minutes (flat 2000.0 before T, then a scripted path):
  - `test_returns_at_horizons` (+1 USD per minute after T → r5 = 5, r120 = 120).
  - `test_excursions_and_vol_exp`.
  - `test_continuation_vs_reversal` (up 5 min then down below P0 by 120 → `cont == 0`).
  - `test_labels_use_blackout_end` (move only between T and T+30 → label60 `"side"`; move of 2 × ATR after Tb → `"up"`; FOMC blackout 3600 shifts Tb).
  - `test_settle_minutes`.
  - `test_reaction_when_market_closed` (no candles in the window → `incomplete == 1`, `p0 is None`, no exception).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(newsintel): measure gold's 1-minute reaction to a release`.

### Task 7: Pre-event features

**Files:** Create `core/newsintel/features.py`; Test `tests/newsintel/test_features.py`

**Interfaces:**
- Consumes: Tasks 1–2, `agents.chief.TFS`, `core.structure.tf_bias`, `core.indicators.atr`.
- Produces: `features(m: Minutes, t: int, prev_t: int | None) -> Features`, dataclass `(t, atr15, atr1h, pre_range, trend_score, hours_since_prev, overlap)`.
  - `trend_score` = Σ over `TFS` of `w × clamp(tf_bias(candles, mult)["score"] / 2.5, −1, 1)` for timeframes with ≥ 60 finished candles before `t` (1d = session days, 4h and 1h and 15m from `resample`), the same formula as `agents.chief.chief`; candles requested: 120 per timeframe.
  - `overlap` = 1 if New York local time at `t` is between 08:00 and 11:59.
  - `hours_since_prev` = (t − prev_t)/3600 or None.
  Only candles finishing at or before `t` may be read.

- [ ] **Step 1: Failing tests:** `test_trend_score_matches_chief_formula` (synthetic uptrend → positive, equals a hand computation using `tf_bias` on the same candles); `test_no_lookahead_features` (replace every candle after `t` with random prices → identical `Features`); `test_overlap_flag` (08:30 NY → 1, 14:00 NY → 0).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(newsintel): pre-event features without lookahead`.

### Task 8: Store and build CLI

**Files:** Create `core/newsintel/store.py`, `core/newsintel/build.py`; Test `tests/newsintel/test_build.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `store.DB = DATA / "news_intel.db"`; `store.connect(path: Path = DB)` context manager (like `journal._db`) creating:
  - `events(id INTEGER PK, kind, name, t, actual, previous, expected, sigma, surprise_z, components TEXT /*json*/)`, unique `(kind, t)`;
  - `reactions(t INTEGER PK, price_source, p0, r5, r15, r30, r60, r120, max_up, max_down, vol_exp, cont, settle_min, atr15, move60, move120, label60, label120, incomplete)`;
  - `features(t INTEGER PK, atr15, atr1h, pre_range, trend_score, hours_since_prev, overlap)`.
- Produces: `store.replace_all(con, events: list[Event], reactions: list[Reaction], feats: list[Features], price_source: str) -> None` — deletes and rewrites all three tables in one transaction.
- Produces: `build.main(argv: list[str] | None = None) -> dict` — CLI `python -m core.newsintel.build --backup <file> [--offline] [--db <path>]`; loads minutes, builds events, keeps events with `t` inside the minutes' range, measures one reaction and one feature row per distinct `t` (blackout 3600 if any event at that `t` is FOMC, else 1800; `prev_t` = previous distinct `t`), writes the DB with `price_source = "spot_backup"`, prints and returns `{"events": n, "times": n, "incomplete": n, "by_kind": {kind: n}}`.

- [ ] **Step 1: Failing tests** (monkeypatch `build_events` to return 3 events, two at the same `t`; small synthetic `Minutes`; temp DB):
  - `test_shared_release_time_one_reaction` → `reactions` has 2 rows, `events` has 3.
  - `test_build_idempotent` → running `main` twice gives identical counts and identical `reactions` rows.
  - `test_events_outside_data_range_skipped`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS; then the full suite `.venv\Scripts\python.exe -m pytest tests -v` → all PASS, and `.venv\Scripts\python.exe tools\smoke_test.py` → passes as before.
- [ ] **Step 5: Real build** (needs `FRED_API_KEY` in `.env`): `.venv\Scripts\python.exe -m core.newsintel.build --backup "C:\Users\mpm\Downloads\trading_research_xauusd_2276 (1).backup"`. Expected: roughly CPI ≈ 79, PPI ≈ 79, PCE ≈ 79, NFP ≈ 79, RETAIL ≈ 79, GDP ≈ 26, CLAIMS ≈ 345, FOMC ≈ 54 events; `incomplete` a small minority (holidays, 2020-03-15). Spot-check 3 events by hand (e.g. CPI 2022-09-13 08:30 NY: gold fell sharply) by printing their reaction rows.
- [ ] **Step 6:** Commit `feat(newsintel): news_intel.db build from backup + FRED`.
