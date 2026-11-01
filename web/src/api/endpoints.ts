import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJSON, sendOk } from './client'
import { xausGet } from './xaus'
import type {
  AccountBody, AdvanceBody, Analysis, BacktestInfo, BacktestStatus, BtResult, CalendarDayDetail, CalendarResp, Calls,
  Candles, Demo, DemoMonth, HealthLatest, JournalAccount, JournalAccounts, JournalTrades, News, OkResult, Review,
  RunBody, RunReply, SaveReply, TradeBody, TradeFilters, TradeReview, XausChart, XausIntraday,
} from './types'

/** Refresh intervals (ms), from the plan's Global Constraints. */
export const DEMO_POLL_MS = 30_000
export const NEWS_POLL_MS = 60_000
export const CALENDAR_POLL_MS = 5 * 60_000
export const BACKTEST_POLL_MS = 1_500
export const ANALYSIS_RETRY_MS = 60_000

/** Old tickNext: next automatic step is due in `next_in_s` (+2 s); after a failure retry in 1 minute. */
export function analysisInterval(q: { state: { status: string; data?: Analysis } }): number {
  if (q.state.status === 'error' || !q.state.data) return ANALYSIS_RETRY_MS
  return (q.state.data.next_in_s + 2) * 1000
}

const tzOff = () => new Date().getTimezoneOffset()

export const qk = {
  analysis: ['analysis'] as const,
  calls: (days: number) => ['calls', days] as const,
  news: ['news'] as const,
  demo: ['demo'] as const,
  demoMonth: ['demo', 'month'] as const,
  calendar: ['calendar'] as const,
  calendarDay: (date: string) => ['calendar', 'day', date] as const,
  btInfo: ['backtest', 'info'] as const,
  btStatus: ['backtest', 'status'] as const,
  btResult: (id: string) => ['backtest', 'result', id] as const,
  btCandles: (a: number, b: number, src?: string) => ['backtest', 'candles', a, b, src ?? ''] as const,
  health: ['health', 'latest'] as const,
  review: ['review'] as const,
  tradeReview: ['trade_review'] as const,
  jAccounts: (archived: boolean) => ['journal', 'accounts', archived] as const,
  jAccount: (id: number) => ['journal', 'account', id] as const,
  jTrades: ['journal', 'trades'] as const,
  xausSpot: ['xaus', 'intraday'] as const,
  xausFut: (interval: string, range: string) => ['xaus', 'chart', interval, range] as const,
}

/* ================= queries ================= */

/** GET /api/analysis — refetches when the server's next 15-minute step is due. */
export const useAnalysis = () =>
  useQuery({ queryKey: qk.analysis, queryFn: () => getJSON<Analysis>('/api/analysis'), refetchInterval: analysisInterval })

/** GET /api/calls?days= (days 0 = off: no request). */
export const useCalls = (days: number) =>
  useQuery({ queryKey: qk.calls(days), enabled: days > 0, queryFn: () => getJSON<Calls>(`/api/calls?days=${days}`) })

/** XAUS 2-5 min spot samples of the last 48 h (old loadSpot). Re-read when the Spot chart opens and every 2 min; retried every minute after a failure. */
export const useSpotSamples = (enabled: boolean) =>
  useQuery({
    queryKey: qk.xausSpot, enabled, refetchOnMount: 'always',
    queryFn: () => xausGet<XausIntraday>('/intraday?symbol=xau&hours=48'),
    refetchInterval: (q) => (q.state.status === 'error' ? 60_000 : 120_000), // live ticks are kept on top of each re-read
  })

/** XAUS COMEX futures candles (old loadFutures); the API caches them ~60 s, so poll every 60 s. */
export const useFuturesChart = (enabled: boolean, interval: string, range: string) =>
  useQuery({
    queryKey: qk.xausFut(interval, range), enabled, refetchOnMount: 'always', refetchInterval: 60_000,
    queryFn: () => xausGet<XausChart>(`/chart?symbol=xau&interval=${interval}&range=${range}`),
  })

/** GET /api/news — 60 s. */
export const useNews = () =>
  useQuery({ queryKey: qk.news, queryFn: () => getJSON<News>('/api/news'), refetchInterval: NEWS_POLL_MS })

/** GET /api/demo — 30 s. */
export const useDemo = () =>
  useQuery({ queryKey: qk.demo, queryFn: () => getJSON<Demo>('/api/demo'), refetchInterval: DEMO_POLL_MS })

/** GET /api/demo/month — polls 1.5 s while the month simulation is running. */
export const useDemoMonth = () =>
  useQuery({
    queryKey: qk.demoMonth, queryFn: () => getJSON<DemoMonth>('/api/demo/month'),
    refetchInterval: (q) => (q.state.data?.status === 'running' ? BACKTEST_POLL_MS : false),
  })

/** GET /api/calendar?tz= — 5 min. */
export const useCalendar = () =>
  useQuery({
    queryKey: qk.calendar, queryFn: () => getJSON<CalendarResp>(`/api/calendar?tz=${tzOff()}`),
    refetchInterval: CALENDAR_POLL_MS,
  })

/** GET /api/calendar/day?date=&tz= */
export const useCalendarDay = (date: string | null) =>
  useQuery({
    queryKey: qk.calendarDay(date ?? ''), enabled: !!date,
    queryFn: () => getJSON<CalendarDayDetail>(`/api/calendar/day?date=${date}&tz=${tzOff()}`),
  })

/** GET /api/backtest/info */
export const useBacktestInfo = () =>
  useQuery({ queryKey: qk.btInfo, queryFn: () => getJSON<BacktestInfo>('/api/backtest/info') })

/** GET /api/backtest/status — 1.5 s only while `active`, otherwise no polling. */
export const useBacktestStatus = (active: boolean) =>
  useQuery({
    queryKey: qk.btStatus, queryFn: () => getJSON<BacktestStatus>('/api/backtest/status'),
    refetchInterval: active ? BACKTEST_POLL_MS : false,
  })

/** GET /api/backtest/result/:id */
export const useBacktestResult = (id: string | null) =>
  useQuery({
    queryKey: qk.btResult(id ?? ''), enabled: !!id, staleTime: Infinity,
    queryFn: () => getJSON<BtResult>(`/api/backtest/result/${id}`),
  })

/** GET /api/backtest/candles?start=&end=[&src=]  (src="backup" for runs whose params.source is set). */
export const useCandles = (start: number | null, end: number | null, src?: string) =>
  useQuery({
    queryKey: qk.btCandles(start ?? 0, end ?? 0, src), enabled: start != null && end != null, staleTime: Infinity,
    queryFn: () => getJSON<Candles>(`/api/backtest/candles?start=${Math.floor(start!)}&end=${Math.floor(end!)}${src ? '&src=' + src : ''}`),
  })

/** GET /api/health/latest */
export const useHealthLatest = () =>
  useQuery({ queryKey: qk.health, queryFn: () => getJSON<HealthLatest>('/api/health/latest') })

/** GET /api/review */
export const useReview = () => useQuery({ queryKey: qk.review, queryFn: () => getJSON<Review>('/api/review') })

/** GET /api/trade_review */
export const useTradeReview = () =>
  useQuery({ queryKey: qk.tradeReview, queryFn: () => getJSON<TradeReview>('/api/trade_review') })

/** GET /api/journal/accounts[?archived=true] */
export const useJournalAccounts = (archived = false) =>
  useQuery({
    queryKey: qk.jAccounts(archived), placeholderData: keepPreviousData,
    queryFn: () => getJSON<JournalAccounts>(`/api/journal/accounts${archived ? '?archived=true' : ''}`),
  })

/** GET /api/journal/accounts/:id */
export const useJournalAccount = (id: number | null) =>
  useQuery({
    queryKey: qk.jAccount(id ?? 0), enabled: id != null,
    queryFn: () => getJSON<JournalAccount>(`/api/journal/accounts/${id}`),
  })

/** GET /api/journal/trades (all records); filters are applied client-side, as the server has none. */
export const useJournalTrades = (filters: TradeFilters = {}) =>
  useQuery({
    queryKey: qk.jTrades, queryFn: () => getJSON<JournalTrades>('/api/journal/trades'),
    select: (d) => ({
      trades: d.trades.filter((t) =>
        (filters.account_id == null || t.account_id === filters.account_id) &&
        (!filters.side || t.side === filters.side) &&
        (filters.phase_id == null || t.phase_id === filters.phase_id)),
    }),
  })

/* ================= mutations ================= */

/** GET /api/analysis?refresh=true — re-runs every agent, then replaces the cached analysis. */
export function useRefreshAnalysis() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await qc.cancelQueries({ queryKey: qk.analysis }) // a plain (cached) GET already in flight must not land after the refresh
      return getJSON<Analysis>('/api/analysis?refresh=true')
    },
    onSuccess: async (d) => {
      await qc.cancelQueries({ queryKey: qk.analysis })
      qc.setQueryData(qk.analysis, d)
    },
  })
}

/** POST /api/backtest/run */
export function useRunBacktest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: RunBody) => sendOk<RunReply>('POST', '/api/backtest/run', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.btStatus }),
  })
}

/** POST /api/health/run  { period } */
export function useRunHealth() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (period: string) => sendOk<RunReply>('POST', '/api/health/run', { period }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.btStatus }),
  })
}

/** POST /api/demo/month/run */
export function useRunDemoMonth() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => sendOk<OkResult>('POST', '/api/demo/month/run'),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.demoMonth }),
  })
}

function useReviewMutation<V>(fn: (v: V) => Promise<OkResult>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    // The analysis is not invalidated here: a plain GET returns the server's cached report and could overwrite a
    // fresh one. Callers that change live weights call useRefreshAnalysis() (GET ?refresh=true) instead.
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.review }) },
  })
}
/** POST /api/review/run  { dry_run } */
export const useRunReview = () => useReviewMutation((dry_run: boolean = false) => sendOk<RunReply>('POST', '/api/review/run', { dry_run }))
/** POST /api/review/undo */
export const useUndoReview = () => useReviewMutation((_?: void) => sendOk<OkResult>('POST', '/api/review/undo', {}))
/** POST /api/review/auto  { on } */
export const useReviewAuto = () => useReviewMutation((on: boolean) => sendOk<OkResult>('POST', '/api/review/auto', { on }))
/** POST /api/review/vote  { agent, on } */
export const useReviewVote = () =>
  useReviewMutation((v: { agent: string; on: boolean }) => sendOk<OkResult>('POST', '/api/review/vote', v))
/** POST /api/review/apply  { run_id } */
export const useApplyReview = () => useReviewMutation((run_id: string) => sendOk<OkResult>('POST', '/api/review/apply', { run_id }))

function useJournalMutation<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: ['journal'] }) })
}
/** POST /api/journal/accounts */
export const useCreateAccount = () => useJournalMutation((b: AccountBody) => sendOk<SaveReply>('POST', '/api/journal/accounts', b))
/** PUT /api/journal/accounts/:id (also used to archive / unarchive) */
export const useUpdateAccount = () =>
  useJournalMutation((v: { id: number; body: AccountBody }) => sendOk<OkResult>('PUT', `/api/journal/accounts/${v.id}`, v.body))
/** POST /api/journal/accounts/:id/advance  { result, note, next_balance } */
export const useAdvancePhase = () =>
  useJournalMutation((v: { id: number; body: AdvanceBody }) => sendOk<SaveReply>('POST', `/api/journal/accounts/${v.id}/advance`, v.body))
/** POST /api/journal/accounts/:id/reopen */
export const useReopenPhase = () =>
  useJournalMutation((id: number) => sendOk<OkResult>('POST', `/api/journal/accounts/${id}/reopen`))
/** POST /api/journal/trades */
export const useCreateTrade = () => useJournalMutation((b: TradeBody) => sendOk<SaveReply>('POST', '/api/journal/trades', b))
/** PUT /api/journal/trades/:id */
export const useUpdateTrade = () =>
  useJournalMutation((v: { id: number; body: TradeBody }) => sendOk<SaveReply>('PUT', `/api/journal/trades/${v.id}`, v.body))
/** DELETE /api/journal/trades/:id */
export const useDeleteTrade = () =>
  useJournalMutation((id: number) => sendOk<OkResult>('DELETE', `/api/journal/trades/${id}`))
