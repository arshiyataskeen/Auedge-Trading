# News Intelligence for the AuEdge XAUUSD agent — design

Date: 2026-10-31 · Status: draft for review · Branch: `feat/news-intelligence`

## 1. Goal

Make the existing AuEdge agent learn from how gold reacted to past US economic releases, find similar past
situations, and use calibrated statistical models as **additional inputs** to the Chief's decision. The existing
architecture, technical analysis, agent weights, Discipline/risk rules and news blackout stay. Nothing places
orders; live execution permissions are unchanged.

Success: a chronological (walk-forward) comparison against today's technical-only agent shows whether the new
inputs improve calibrated forecasts **and** do not worsen trading results. If they don't, the layer stays
advisory (explanations, volatility expectations, AVOID gates only).

### Baseline to beat (measured 2026-10-31)

`backtest.web_run`, 15m steps, 2026-05-26 → 2026-08-14, spot candles from the user's `trading_research` backup:
61 trades, win rate 49 %, +1.08R total (+0.02R/trade), max drawdown 12R ($2,795 at 0.1 lot), +$680 on $25,000.
Chief confidence ≥ 70 %: 45 trades, +5.29R. Agents' 4-hour direction calls: 45–56 %.

## 2. Decisions made

| Question | Decision |
|---|---|
| Source of Actual vs Forecast | Official first-release actuals (FRED/ALFRED vintages); surprise measured against a statistical expectation, not consensus |
| Go-live bar | Better out-of-sample calibrated forecasts (log-loss) than technical-only **and** R/trade not lower, max drawdown not higher |
| Integration | New `core/newsintel/` package + advisory `news_intel` agent + one walk-forward-validated stacker in the Chief |
| New dependencies | `numpy`, `scikit-learn` |
| Use of news layer (2026-11-01, after sub-project 2) | **Risk only.** Walk-forward on 456 out-of-sample releases (2022Q1–2026Q2): no news model beat technical-only on direction (Bayes 1.077, Forest 1.074, LogReg 1.109, KNN 1.321 vs technical 1.053 log-loss; all significantly worse). The volatility forecast beat naive (MAE $4.81 vs $5.11). User decision: the news layer feeds expected volatility and AVOID gates only; it never changes BUY/SELL direction or confidence. The stacker / `NEWSINTEL_MODE=live` direction path in §7 is dropped. |

## 3. Sub-projects (each gets its own plan → build → review)

1. **Event & reaction dataset** (this spec's first plan)
2. **Models & walk-forward harness**, report vs baselines
3. **Integration**: `news_intel` agent, stacker, M5 confirmations, AVOID gates, explanations
4. **Learning loop**: frozen predictions, post-event scoring, gated retraining

## 4. Data available

- `trading_research` Postgres backup (`ohlcv_xauusd`): spot XAUUSD bid, **1-minute 2020-01-01 → 2026-08-15**
  (2.35 M rows, no bad OHLC, no gaps > 3.2 days), daily 2003 → 2025. No ask prices → historical spread unknown.
- Live feed (`core/data.py`): futures 1m (1 day), 5m (5 days), 15m, 1h, 1d; spot samples.
- `core/news.py`: official CPI/NFP dates 2026–27, FOMC 2025–27; ForexFactory current week (forecast/previous,
  no actual). No historical actual/forecast anywhere.
- A pure-Python reader for pg_dump custom format (PGDMP 1.16, gzip) already exists from the backtest work and
  moves into the repo as `tools/pgdump_read.py`.

## 5. Sub-project 1 — event & reaction dataset

### 5.1 Event calendar 2020 → now

| Kind | Source of dates + first-release actual | Release time (New York) |
|---|---|---|
| CPI, Core CPI | ALFRED vintages of `CPIAUCSL`, `CPILFESL` (m/m computed from the vintage) | 08:30 |
| PPI | ALFRED `PPIFIS` | 08:30 |
| PCE, Core PCE | ALFRED `PCEPI`, `PCEPILFE` | 08:30 |
| NFP, Unemployment rate | ALFRED `PAYEMS` (change), `UNRATE` | 08:30 |
| GDP (advance) | ALFRED `GDPC1` (real GDP; first vintage of each quarter, annualised q/q) | 08:30 |
| Retail sales | ALFRED `RSAFS` | 08:30 |
| Initial jobless claims | ALFRED `ICSA` | 08:30 Thu |
| FOMC decision | Hard-coded Fed calendar 2020–2024 (incl. 2020-03-03 and 2020-03-15 emergency moves) + existing lists | 14:00 (emergency: actual time) |
| ISM Mfg/Services PMI, ADP | Not on FRED. Dates only from the publishers' calendars; actuals only if the user approves a source | 10:00 / 08:15 |

The release date is the vintage's `realtime_start`. Release times are fixed per kind; known exceptions (e.g.
government-shutdown delays) come out of the vintage dates automatically. FRED needs a free API key the user
registers (`FRED_API_KEY` in the existing env handling, `core/env.py`). Downloads are cached in
`data/news_intel/fred/` so rebuilds are offline.

### 5.2 Surprise proxy (no lookahead)

For each series and event *i*: `surprise_z = (actual_i − expected_i) / σ_i`, where `expected_i` is an AR(1)
forecast fitted on **first-release values published before event i** (expanding window, min 24 points;
before that: last value), and `σ_i` = 1.4826 × MAD of that model's last 36 one-step errors (`z` null if
σ < 1e-12). Releases for observation periods 2020-03-01 … 2021-06-30 (COVID shock) are left out of the fit and
error history of later releases. A release whose prior period was never published (e.g. October 2025 after the
shutdown) has no one-step change: `actual` and its surprise are null. Sign is
oriented so that **positive = hawkish/strong-USD** (e.g. higher CPI, higher NFP, lower unemployment, lower claims).
FOMC has no free surprise measure: modelled by event kind + pre-event conditions only, `surprise_z = null`.

### 5.3 Reaction measurement (from 1-minute candles)

Baseline `P0` = close of the last 1-minute candle finishing at or before release time `T`.

- Returns at T+5, +15, +30, +60, +120 min (USD and ÷ pre-event M15 ATR)
- MFE / MAE over 120 min
- Volatility expansion = high−low over T…T+30 ÷ high−low over T−60…T
- Continuation vs reversal = sign(ret +5) vs sign(ret +120)
- Time to stabilise = first minute after T where the rolling 5-min range ≤ 1.5 × the median 5-min range of T−60…T
- **Tradable label** (used by models): return from blackout end `Tb` (T+30, FOMC T+60) to `Tb+60`, classified
  up / down / sideways with sideways = |move| < 0.5 × pre-event M15 ATR. Secondary label: `Tb` → `Tb+120`.

Events with fewer than 90 % of expected 1-minute candles in T−60…T+180 are kept but flagged `incomplete` and
excluded from model training.

### 5.4 Pre-event features (only candles closed before T)

M15 ATR(14), H1 ATR(14), realised range of T−60…T, Chief `tf_bias` weighted score (reusing `agents/chief.py`
functions on candles resampled from the 1-minute data), event kind, `surprise_z`, hours since previous
high-impact event, session (London/NY overlap flag).

### 5.5 Storage

`data/news_intel.db` (SQLite, same style as `journal.db`):

- `events(id, kind, name, t, actual, previous, expected, sigma, surprise_z, source)`
- `reactions(event_id, price_source, p0, r5, r15, r30, r60, r120, mfe, mae, vol_exp, cont, settle_min, label60, label120, incomplete)`
- `features(event_id, atr15, atr1h, pre_range, trend_score, hours_since_prev, overlap)`
- `predictions(...)`, `model_versions(...)` — created in sub-projects 2/4.

Build: `python -m core.newsintel.build --backup <file.backup>` (idempotent; re-running replaces derived rows).

## 6. Sub-project 2 — models & walk-forward harness

- **Validation**: expanding-window walk-forward, test fold = one calendar quarter, 1-day embargo, all
  hyper-parameters chosen by inner time-ordered CV on the training part only. Random seeds fixed.
- **Baselines**: (0) climatology per event kind; (1) technical-only = Chief weighted score → multinomial LR.
- **Models**
  - Descriptive stats per kind × surprise bucket: mean, median, sd, P(up/down/side), volatility quantiles.
  - Bayesian: Dirichlet-multinomial; prior = pooled class frequencies shrunk toward the event kind
    (strength tuned by inner CV); evidence = binned surprise (sign × |z| ≥ 1), trend state, pre-vol tercile.
    Gives pre-release P and a post-release update once `surprise_z` is known.
  - KNN: standardised [surprise_z, pre_range/ATR, atr15, trend_score, kind one-hot × w], distance-weighted,
    k ∈ 5…10 by inner CV; returns neighbour event ids for explanations.
  - Bhattacharyya distance between histograms of ATR-normalised tradable moves (neighbour set vs kind
    overall; kind vs kind). Diagnostic and uncertainty input only — never a direction signal.
  - Logistic regression: multinomial, L2, standardised; coefficients + per-fold permutation importance.
  - Random forest: evaluated; kept only if OOS log-loss beats LR with a paired bootstrap 95 % CI excluding 0.
- **Selection**: primary news model = lowest OOS log-loss; calibrated (temperature scaling) on training data.
  Bayes/KNN/LR are correlated (same features), so they are **not** averaged; non-primary models are reported
  as diagnostics and explanations.
- **Stacker**: multinomial LR on [technical score, primary-model log-odds], trained walk-forward.
- **Go-live check**: stacker log-loss < technical-only with paired-bootstrap 95 % CI excluding 0 **and**, in
  `backtest.py` runs with the stacker in live mode vs off, R/trade not lower and max drawdown not higher.
- **Report** (HTML in `data/`, like the existing backtest reports): log-loss, Brier, accuracy, reliability
  curves, predicted vs actual volatility; overall and for NFP / CPI / FOMC / other; per-fold table.

## 7. Sub-project 3 — integration

> **Superseded in part (2026-11-01):** risk-only use was decided (see §2). Build only the volatility expectation,
> the AVOID gates, the explanation (similar past releases, expected range) and the post-event learning of the
> volatility forecast. Drop the direction stacker and `NEWSINTEL_MODE=live`; the agent never votes or changes
> the Chief's direction or confidence. The trading half of the go-live check becomes: with the AVOID gates on vs
> off in `backtest.py`, R per trade not lower and max drawdown not higher.

- `agents/news_intel.py`: `NewsIntelAgent(BaseAgent)` with `votes=False`, `weight=0`, added to `BUILT_IN`.
  Loads model artifacts from `data/news_intel/models/`. Within 24 h before an event: expected volatility and
  pre-release probabilities; after release: posterior with known surprise, 5–10 similar events with their moves,
  Bhattacharyya coherence, calibrated confidence. Outside event windows: neutral "no news context".
  `AgentResult` gains an optional `extra: dict = {}` (backward compatible).
- **Chief stacker** behind `NEWSINTEL_MODE = off | advisory | live` (default `advisory`):
  advisory = shown only; live = may lower confidence, turn BUY/SELL into WAIT when P(side) is weak, raise
  confidence only up to `MAX_CONFIDENCE`. It never creates a trade; existing entry conditions (hunt + reclaim or
  15m break) remain required. `live` may only be set after the go-live check passes (recorded in the report).
- **M5 confirmations**: M5 break of structure and break-and-retest built from `core/structure.py` helpers on
  the live 5m candles; shown as chips and fed to the stacker as features; they become entry requirements only
  if they pass the same walk-forward check.
- **AVOID gates** in `agents/psychology.assess` and `backtest.block_reason` (block only):
  blackout extended to the full event calendar (30 min before / 30 after, FOMC keeps 60 after);
  abnormal volatility (current M5 range/ATR above the 99th percentile of non-event history);
  spread expansion (> 3 × median, live only); high uncertainty inside an event window (near-uniform predicted
  distribution or high neighbour Bhattacharyya distance; thresholds set from the harness).
- **Explanations** in the Chief report: probabilities, supporting events with dates and moves, expected range.
- BUY / SELL / WAIT outputs unchanged; AVOID = a blocking gate fired (shown as today's psychology blocks are).

## 8. Sub-project 4 — learning loop

- Predictions are frozen with timestamps when first produced (pre and post release) in `predictions`.
- At T+150 min the app's existing 15-minute background check scores each event from live 1m/5m candles:
  tradable move, MFE/MAE, range, hit, Brier, log-loss, predicted vs actual volatility; appends the reaction
  (price_source = `futures_live`, moves ATR-normalised).
- Tracked by kind (NFP / CPI / FOMC / other) and by direction; API endpoint + a card in the Track record tab.
- Stats and Bayes counts update after every event. KNN/LR/stacker retrain only after ≥ 20 new events, through
  the same harness; challenger replaces champion only if OOS log-loss on the latest unseen quarter is not worse.
  Versions kept in `model_versions`. Mode changes (advisory → live) and rule changes are never automatic.

## 9. Testing

- Unit tests (pytest, new `tests/` folder) for: surprise proxy (no use of future vintages), reaction metrics on
  synthetic candles, label thresholds, walk-forward splitter (no train/test overlap, embargo respected),
  Bhattacharyya on known distributions, gates.
- Leakage test: shuffling future candles after T must not change any feature.
- Existing `tools/smoke_test.py` must keep passing; agent pipeline runs with `NEWSINTEL_MODE=off` must produce
  identical Chief output to today.

## 10. Out of scope

Consensus forecasts, live order execution, changing existing agent weights or Discipline limits, non-USD events,
a new UI tab (only cards/chips inside existing tabs).

## 11. Risks

- ~6.5 years gives roughly 50–80 events per monthly kind, ~340 claims: per-kind models are thin, hence pooling.
- Proxy surprise is weaker than consensus surprise; the harness will show whether it carries signal.
- Backup is spot, live is futures: moves are ATR-normalised; the gap is not modelled.
- It is a legitimate outcome that the directional models show no edge; then only the volatility expectation and
  AVOID gates are used.
