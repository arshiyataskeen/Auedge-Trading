# Agent Enhancements (gap list) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Add the intelligence the gap analysis (`.superpowers/sdd/gap-analysis-2026-11-01.md`) found missing, without changing the user's trading rules or strategy.

**Architecture:** One new pure module per capability under `core/intel/`, each returning a small dataclass + plain-language text. The Chief gets a `quality` block (0–100 factor score + AVOID) built from them. Every capability that can block or change a trade sits behind a flag in `core/intel/flags.py` (env `INTEL_<NAME>=on|off`, all default **off**), so live trades and backtests are unchanged until the user turns one on after the performance test. Display (card rows, reasons, score) is always on.

**Tech:** Python 3, pytest, existing `core/structure.py`, `core/liquidity.py`, `core/indicators.py`, `core/newsintel/*`; React `web/` for one "Setup quality" card.

**Spec:** the user's 13-point enhancement brief (2026-11-01) + gap analysis. Trading rules (risk %, trades/day, RR, entry timeframe, partials) are **out of scope — do not change them**.

## Global Constraints
- No change to existing trade decisions while all `INTEL_*` flags are off: Chief report decision fields and backtest trades on 2026-10-01..10-30 (15m) must be identical (24 trades, +5.66R).
- Only closed candles before `ctx.generated_at`; no look-ahead.
- Plain-language text for a trader. Never call the score a probability.
- New-York time via ZoneInfo for sessions/opens (DST-safe); one shared session helper.
- Backtest metrics added must use existing spread; slippage stays a parameter.
- Commit with explicit `git add`; never restart :8000; GET only against the live server.

## Tasks
1. **Levels & HTF alignment** — `core/intel/levels.py`: daily open, weekly open (NY 17:00 roll), London/NY session high/low, previous session high/low, premium/discount of the H1 dealing range; `core/intel/align.py`: H1 structure + M15 trend → aligned_up / aligned_down / mixed. Flag `INTEL_ALIGN`: when on, Chief turns a BUY/SELL against an aligned H1+M15 into WAIT. Tests incl. DST weeks.
2. **Sessions (one helper)** — `core/intel/sessions.py`: Asian/London/NY/overlap windows in NY time, replace the two inconsistent Asian-range definitions (liquidity.py, ict.py) with it (behaviour-preserving test for each caller), London-open and NY-open sweep flags. Flag `INTEL_SESSION` (when on: no new entry in the low-liquidity window 17:00–19:00 NY unless score ≥ 70).
3. **Sweep → BOS and structure quality** — `core/intel/structure_q.py`: sweep followed by candle-close BOS within N bars, displacement (body ≥ 0.6 range and range ≥ 1.2 ATR), breakout body strength, failed-breakout detection; M5 BOS+retest from `core/newsintel/m5.py` as a factor. Flag `INTEL_SWEEP_BOS` (when on: Chief entry trigger requires sweep→BOS or M5 BOS+retest).
4. **FVG + order/breaker/rejection blocks** — `core/intel/zones.py`: last opposing candle before displacement = order block; broken OB = breaker; long-wick rejection block; unmitigated FVGs near price. Confluence only (score factor), no flag needed.
5. **Volatility regime & stop cap** — `core/intel/volatility.py`: ATR percentile regime (low/normal/high/abnormal), expansion/contraction (ATR slope), max stop distance = k × ATR15 (k from history, 99th pct of current stops). Flag `INTEL_VOL` (when on: abnormal → AVOID; stop beyond cap → skip, never widen risk).
6. **Entry checks** — `core/intel/entry.py`: distance from breakout (> x ATR = late), retest still valid, room to nearest opposing liquidity/S/R ≥ planned target (else "target blocked"). Flag `INTEL_ENTRY`.
7. **News extras** — FRED 10y Treasury (DGS10) and 10y real yield (DFII10) daily change into the news card/rows; add ISM manufacturing PMI, jobless claims (already in calendar kinds) and FOMC speeches (ForexFactory "Fed Chair"/"FOMC Member" titles) to the blackout calendar (`core/news.py` kinds map) behind flag `INTEL_NEWS_EXTRA`.
8. **Quality score + AVOID + output** — `core/intel/score.py`: weights in `data/intel_weights.json` (defaults in code), factors = H1/M15 alignment, sweep, BOS, retest, displacement, FVG/OB confluence, session, news risk, volatility, (spread n/a → neutral); score 0–100 with a per-factor breakdown; bands 85/70/55 configurable; `ChiefReport.quality` + `AVOID` label when a blocking gate fires or score < 55 (label only unless flag `INTEL_SCORE_GATE`). React "Setup quality" card on Trade page Plan + Agents.
9. **Backtest breakdowns & per-factor variants** — backtest summary by session, volatility regime, news category; slippage parameter in the summary; `--intel <flags>` CLI/web option to run variants (existing, +each flag, all) so the user's later performance comparison is one command. Calibration of score thresholds by walk-forward is part of that later comparison (not this plan).

Each task: TDD → task review → fix → re-review; Task 8 browser check desktop/375, dark/light.
