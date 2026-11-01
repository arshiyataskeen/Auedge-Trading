// Types written from real /api/* responses (server on :8000). Fields the UI does not read yet are left loose.

export type Side = 'BUY' | 'SELL'
export type OkResult = { ok: boolean; error?: string }

/* ---------- analysis ---------- */
export type AgentView = {
  agent: string; status: string; bias: string; confidence: number; headline: string
  reasons: string[]; warnings: string[]; levels: AgentLevel[]; timeframe: string; veto: boolean
  metrics: Record<string, number | string>; subtitle: string; bias_label: string; rows: [string, string][]; summary: string
  label?: string; weight?: number; base_weight?: number; vote_off?: boolean; perf_weight?: number
  /** Performance weighting (60 days of scored calls); null until an agent has any. */
  perf?: AgentPerf | null
  /** news_intel only: the Intel fields plus mode. */
  extra?: Record<string, unknown>
}
export type AgentLevel = { kind: string; price: number; note?: string }
export type AgentPerf = { hits: number; n: number; hit_rate: number; shrunk: number; mult: number }
/** Scored calls of one agent (or "chief"); hit_rate is null until something was decided. */
export type AgentRecord = { hits: number; misses: number; flat: number; pending: number; hit_rate: number | null }
export type TrackTrade = { ts: number; side: Side; entry: number; stop: number; t1: number; status: string; result_r: number | null }
export type Track = {
  agents: Record<string, AgentRecord>
  trades: { won: number; lost: number; open: number; expired: number; win_rate: number | null; avg_r: number | null; recent: TrackTrade[] }
}
export type StopPool = { price: number; side: string; strength: number; sources: string[]; status: string; hunted_ago_min: number | null }
export type TradePlan = {
  kind: string; action: string; side: Side | null
  entry_lo: number | null; entry_hi: number | null; stop: number | null; be_at: number | null
  t1: number | null; t2: number | null; rr1: number | null; rr2: number | null
  steps: string[]; cancel_if: string
}
export type Chief = {
  bias: string; confidence: number; confidence_word: string; weighted_score: number
  htf_label: string; intraday_label: string; price: number
  timeframes: { tf: string; bias: string; text: string; weight: number; role: string }[]
  chips: { agent: string; label: string; bias: string }[]
  headline: string; verdict: string; buy_zone: number[]; sell_zone: number[]
  plan: TradePlan; stops_above: StopPool[]; stops_below: StopPool[]; recent_hunt: unknown
  levels: unknown[]; reasons: string[]; warnings: string[]; ai_written: boolean
  today: { side: string; trend: string; tfs: string; text: string; buy_below: number; sell_above: number }
  day_range: number
  quality?: Quality
}
export type QualityFactor = { name: string; label: string; ok: boolean | null; weight: number; points: number; text: string }
export type Quality = {
  score: number; band: string; avoid: boolean; label: string; avoid_reasons: string[]; factors: QualityFactor[]; text: string
  flags_on?: string[]
}
export type IntelFlag = { name: string; on: boolean; text: string; by?: string | null; at?: number | null; note?: string | null }
export type Analysis = {
  ai_enabled: boolean; generated_at: string; next_in_s: number
  spot: { price: number; updated_at: string; age_seconds: number; stale: boolean; price_source: string }
  futures_gap: number; data_errors: string[]; adapter_problems: string[]
  data_check: AgentView; chief: Chief; agents: AgentView[]
  track: Track | null
  weights_week: unknown; perf_weights_on: boolean
}

/* ---------- trades (backtest / demo / calls) ---------- */
export type BtTrade = {
  side: Side; kind: string; decided_t: number; entry_t: number; entry: number; stop: number; t1: number
  exit_t: number; exit: number; why: string; r: number; conf?: number; usd?: number | null; balance?: number | null
  source?: string; run?: string; open?: boolean; half?: boolean; gap?: number
}
export type Calls = { days: number; calls: BtTrade[] }

export type BtSummary = {
  n: number; wins: number; losses: number; win_rate: number | null; avg_r: number | null; total_r: number; max_dd: number
  streak: number; targets: number; stops: number; breakeven: number; half_at_1r: number; expired: number
}
export type BtUsd = {
  account: number; lot: number; total_usd: number; end_balance: number; return_pct: number; max_dd_usd: number
  avg_usd: number; best_usd: number; worst_usd: number; avg_risk_usd: number
}
export type BtParams = {
  start: number; end: number; step: string; spread: number; target_rr: number | null; partial: boolean; account: number; lot: number
  news: boolean; adaptive: boolean; day_max_loss: number; day_max_profit: number; live_rules: boolean; stop_slip: number
  f_session: boolean; f_trend: boolean; f_htf: boolean; f_htf_strict: boolean; f_hunt: boolean
  runner_rr: number | null; trail_r: number | null; min_conf: number | null; drop: unknown; cache: boolean
  source?: string
}
export type BtStep = {
  t: number; p: number; a: string; k: string; sd: Side | null; cf: number; sc: number; tr: string
  lv: (number | null)[]; up: number[]; dn: number[]; ag: [string, string, number, string | null][]
}
export type BtResult = {
  steps: BtStep[]; params: BtParams; summary: BtSummary; usd: BtUsd | null
  groups: Record<string, BtSummary>; agents: Record<string, Record<string, unknown>>
  lines: string[]; counts: Record<string, unknown>; equity: [number, number][]; trades: BtTrade[]; made_at: number
}
export type BtRunInfo = BtParams & {
  id: string; made_at: number; n: number; win_rate: number | null; total_r: number; total_usd: number | null
}
export type BacktestInfo = {
  range: { first_1h: number; first_15m: number; last: number; cached: boolean }
  runs: BtRunInfo[]
}
export type BacktestStatus = {
  running: boolean; id?: string; kind?: string; progress?: { done: number; total: number; phase?: string }; elapsed?: number; pct?: number; message?: string
  done?: boolean; error?: string; [k: string]: unknown
}
export type Candle = { t: number; o: number; h: number; l: number; c: number }
export type Candles = { tf: string; sec: number; candles: Candle[]; error?: string }

export type RunBody = {
  start: string; end: string; step: string; spread: number; account: number; lot: number; target_rr: number | null
  partial: boolean; adaptive: boolean; day_max_loss: number; day_max_profit: number; live_rules: boolean
  f_session: boolean; f_trend: boolean; f_hunt: boolean; stop_slip?: number
}
export type RunReply = OkResult & { id?: string }

/* ---------- health check ---------- */
export type HealthVariant = {
  key: string; group: string; label: string; n: number; win_rate: number | null; usd: number; dd: number
  h1_usd: number; h2_usd: number; h1_n: number; h2_n: number; blocked: Record<string, number>; verdict: string; note: string
}
export type HealthLatest = { id: string; kind: string; made_at: number; variants: HealthVariant[]; params: Partial<BtParams> } | { error: string }

/* ---------- demo ---------- */
export type DemoTrade = {
  id: number; ts: number; side: Side; entry: number; stop: number; t1: number; gap: number; lot: number; cost: number
  status: string; closed_ts?: number; result_r?: number; half: number; exit_price?: number; usd?: number; why?: string; be: number
  stop_now?: number; unrealised?: number
}
export type Demo = {
  start: number; lot: number; balance: number; equity: number; realised: number; today: number; week: number
  trades: number; wins: number; win_rate: number; open: DemoTrade[]; closed: DemoTrade[]
  curve: [number, number][]; price: number; journal_account: number
}
export type DemoMonth = { status: 'none' | 'running' | 'done' | 'error' | string; id?: string; result?: BtResult; error?: string }

/* ---------- calendar ---------- */
export type CalendarDay = { pnl: number; trades: number; nows: number; live: boolean; sim: boolean }
export type CalendarResp = { days: Record<string, CalendarDay> }
export type CalendarDayDetail = {
  date: string; source: string; steps: number; nows: number; pnl: number; window: [number, number]
  timeline: { t: number; p: number; a: string; k: string; sd: Side | null; cf: number; tr: string; lv: (number | null)[] }[]
  agents: Record<string, { calls: number; hit: number; miss: number; flat: number; pending: number }>
  trades: BtTrade[]; levels: { start: BtStep; end: BtStep }; error?: string
}

/* ---------- news ---------- */
export type NewsEvent = {
  t: number; name: string; impact: string; forecast: string; previous: string; blocks: boolean
  win_from: number; win_to: number; source: string
}
export type News = { now: number; blocking: NewsEvent | null; events: NewsEvent[] }

/* ---------- review board / trade review ---------- */
export type ReviewChange = { agent: string; action: 'on' | 'off'; gain_6m?: number; gain_month?: number; halves_6m?: [number, number] }
export type ReviewCandidate = {
  agent: string; action: 'on' | 'off'; gain_6m: number; halves_6m: [number, number]; gain_month: number; skipped?: string
}
export type Review = {
  votes: { off: string[]; auto_apply: boolean }
  log: { t: number; by: string; before: string[]; after: string[]; changes: ReviewChange[]; note: string; review: string | null }[]
  last: {
    id: string; made_at: number; apply: boolean; applied?: boolean; votes_before: string[]; votes_after: string[]
    changes: ReviewChange[]; candidates: ReviewCandidate[]; confirm: { result?: string } | null; summary: string
    rules: { noise_usd: number; max_changes: number; min_voters: number }
  } | null
  agents: { name: string; label: string; weight: number }[]
  filters?: IntelFlag[]
  next_due: number
}
export type ReviewedTrade = {
  t: number; side: Side; r: number; usd: number; won: boolean; why: string; for: string[]; against: string[]
  reasons: string[]; tags: Record<string, string>; src: string
}
export type TradeReview = {
  made_at: number; backtest: string; n_live: number; n_backtest: number
  live: ReviewedTrade[]; recent_backtest: ReviewedTrade[]
  agents: { agent: string; helped: number; hurt: number; n: number; acc: number; verdict: string }[]
  lessons: string[]; win_patterns: string[]
  conditions: { cond: string; val: string; n: number; win: number; avg_r: number; total_r: number }[]
  reasons: Record<string, number>; early_review_at: number
  labels: Record<string, string>; voting_off: string[]; reason_text: Record<string, string>; win_text: Record<string, string>
}

/* ---------- journal ---------- */
export type PhaseRules = {
  name: string; target_pct: number | null; daily_loss_pct: number | null; max_loss_pct: number | null
  max_loss_type: string; min_days: number; consistency_pct: number | null; profit_split?: number | null
}
export type AccountRules = { phases: PhaseRules[]; funded: PhaseRules; reset: string; daily_base: string }
export type RRStats = {
  n_with_stop: number; n_without_stop: number; avg_planned: number | null; avg_achieved: number | null
  avg_win_r: number | null; avg_loss_r: number | null; breakeven_win_rate: number | null; win_rate: number | null
  expectancy_usd: number | null; expectancy_r: number | null; hit_target: number; with_target: number
  dist: { label: string; n: number }[]
}
export type Consistency = {
  limit_pct: number | null; best_day: { day: string; pnl: number } | null; best_day_share: number | null; ok: boolean | null
  profit_needed: number | null; win_days: number; loss_days: number; avg_win_day: number | null; avg_loss_day: number | null
  worst_day: number | null; biggest_trade_share: number | null; avg_lots: number | null; max_lots: number | null
  min_lots: number | null; lot_spread: number | null
}
export type PhaseStats = {
  n: number; open: number; wins: number; losses: number; win_rate: number | null; avg_win: number | null; avg_loss: number | null
  profit_factor: number | null; best: number | null; worst: number | null; avg_r: number | null
  followed_plan_pct: number | null; followed_pnl: number | null; broke_pnl: number | null
  by_setup: { setup: string; n: number; pnl: number; win_rate: number }[]
  by_emotion: { emotion: string; n: number; pnl: number }[]
}
export type PhaseCheck = {
  rules: PhaseRules; status: string; breach: { text: string } | null; balance: number; profit: number
  target_amt: number | null; target_left: number | null; days_traded: number; min_days: number
  daily_limit: number | null; today_pnl: number; daily_room: number | null; max_floor: number | null; max_room: number | null
  equity: [number, number][]; days: { day: string; pnl: number; n: number }[]
  rr: RRStats; consistency: Consistency; stats: PhaseStats
}
export type Phase = {
  id: number; account_id: number; idx: number; name: string; start_balance: number; started_at: number
  ended_at: number | null; result: string | null; note: string | null; check: PhaseCheck; is_funded?: boolean
}
export type JournalTrade = {
  id: number; account_id: number; phase_id: number; opened_at: number; closed_at: number | null; side: Side; symbol: string
  lots: number; entry: number; stop: number | null; target: number | null; exit: number | null; pnl: number | null
  commission: number; setup: string; source: string; auedge: Record<string, unknown> | null; emotion: string | null
  followed_plan: number | null; mistakes: string; notes: string; rating: number | null; image: string | null
  created_at: number; net: number; r: number | null; planned_rr: number | null; day: string
  account?: string; account_size?: number; archived?: number; phase?: string; phase_idx?: number
}
export type JournalAccount = {
  id: number; name: string; firm: string; size: number; created_at: number; rules: AccountRules; notes: string
  archived: number; phases: Phase[]; current?: Phase | null; total_phases?: number; trades?: JournalTrade[]
  /** list endpoint only */
  n_trades?: number; last_trade_at?: number | null
  error?: string
}
export type JournalAccounts = { accounts: JournalAccount[]; now: number }
export type JournalTrades = { trades: JournalTrade[] }
export type TradeFilters = { account_id?: number; side?: Side | ''; phase_id?: number }
/** Body for creating/editing a journal trade (shape built by the old tradeBody()). */
export type TradeBody = Record<string, unknown> & { account_id?: number; opened_at?: number | null }
export type AccountBody = { name: string; firm?: string; size?: number; notes?: string; rules?: Partial<AccountRules> | Record<string, unknown>; archived?: boolean }
export type SaveReply = OkResult & { id?: number }
export type AdvanceBody = { result: string; note?: string; next_balance?: number | null }

/* ---------- XAUS candles (the chart; GET only, from the free XAUS API) ---------- */
export type XausIntraday = { interval_seconds?: number; source?: string; points: { t: number; p: number | null }[] }
export type XausChart = { points: { t: number; o: number | null; h: number; l: number; c: number | null; v?: number }[] }

export type SeparationDrift = {
  recent_n: number; prior_n: number; recent_distance: number; prior_distance: number
  recent_mean: number; prior_mean: number; diff: number; lo: number; hi: number; flag: boolean
}
export type SeparationRow = {
  agent: string; n: number; mean: number | null; hit_rate: number | null
  distance: number | null; lo: number | null; hi: number | null
  verdict: 'useful' | 'none' | 'harmful' | 'too_few'; drift: SeparationDrift | null; source: string
}
