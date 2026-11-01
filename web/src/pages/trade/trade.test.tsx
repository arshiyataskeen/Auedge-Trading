import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AppShell from '../../components/AppShell'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import TradePage from './index'
import { TF, aggregate, fmtLeft, levelRows, sizeInfo, tradingDay, withTick } from './logic'

const m = vi.hoisted(() => {
  const series = {
    setData: vi.fn(), setMarkers: vi.fn(), createPriceLine: vi.fn((_o?: unknown) => ({ applyOptions: vi.fn() })), removePriceLine: vi.fn(),
    update: vi.fn(), priceToCoordinate: vi.fn(() => 10),
  }
  const hist = { setData: vi.fn() }
  const chart = {
    addCandlestickSeries: vi.fn(() => series), addHistogramSeries: vi.fn(() => hist), remove: vi.fn(), applyOptions: vi.fn(),
    priceScale: vi.fn(() => ({ applyOptions: vi.fn() })), subscribeClick: vi.fn(), unsubscribeClick: vi.fn(),
    timeScale: vi.fn(() => ({ fitContent: vi.fn(), timeToCoordinate: vi.fn(() => 10) })),
  }
  const subs = new Set<() => void>()
  const live = { price: 4095 as number | null, updatedAt: 0, source: 'x', status: 'live', change: null }
  const setLive = (price: number, updatedAt: number) => { Object.assign(live, { price, updatedAt }); subs.forEach((f) => f()) }
  return { series, hist, chart, createChart: vi.fn(() => chart), live, subs, setLive }
})
vi.mock('lightweight-charts', () => ({ createChart: m.createChart, CrosshairMode: { Normal: 0 }, LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 } }))
vi.mock('../../api/live', async () => {
  const { useEffect, useState } = await import('react')
  return { useLivePrice: () => { const [, f] = useState(0); useEffect(() => { const g = () => f((x) => x + 1); m.subs.add(g); return () => { m.subs.delete(g) } }, []); return { ...m.live } } }
})

const agent = (name: string, label: string, o: Record<string, unknown> = {}) => ({
  agent: name, status: 'OK', bias: 'WAIT', confidence: 40, headline: `${label} headline`, reasons: [], warnings: [], levels: [],
  timeframe: '1h', veto: false, metrics: {}, subtitle: '', bias_label: 'RANGE', rows: [], summary: `${label} summary`, label, weight: 1, base_weight: 1, ...o,
})
const PLAN = {
  kind: 'now', action: 'BUY NOW', side: 'BUY', entry_lo: 4090, entry_hi: 4094, stop: 4080, be_at: 4104, t1: 4116, t2: null, rr1: 2,
  steps: ['Place a buy limit inside the zone', 'Stop first'], cancel_if: 'a 15m candle closes below 4085',
}
const chief = (plan: Record<string, unknown>) => ({
  bias: 'BUY', confidence: 72, confidence_word: 'high', weighted_score: 3, htf_label: 'BUY', intraday_label: 'BUY', price: 4095,
  timeframes: [{ tf: 'Daily', bias: 'BUY', text: 'Daily is up', weight: 30, role: 'trend' }, { tf: '15m', bias: 'WAIT', text: 'Waiting', weight: 10, role: 'pullback' }],
  chips: [{ agent: 'wyckoff', label: 'BUY', bias: 'BUY' }, { agent: 'elliott', label: 'SELL', bias: 'SELL' }],
  headline: 'Buy the dip', verdict: 'Because trend is up.', buy_zone: [4090, 4094], sell_zone: [4120, 4125], plan,
  stops_above: [{ price: 4130, side: 'buy', strength: 5, sources: ['PDH'], status: 'untouched', hunted_ago_min: null }],
  stops_below: [{ price: 4070, side: 'sell', strength: 4, sources: ['PDL'], status: 'hunted', hunted_ago_min: 12 }],
  recent_hunt: null, levels: [], reasons: ['r1'], warnings: [], ai_written: false,
  today: { side: 'BUY', trend: 'UP', tfs: 'D 4H', text: 'Trend is up today', buy_below: 4090, sell_above: 4130 }, day_range: 60,
})
const ANALYSIS = (plan: Record<string, unknown> = PLAN, at = '2026-10-31T10:00:00Z') => ({
  ai_enabled: false, generated_at: at, next_in_s: 600, perf_weights_on: false, adapter_problems: [], data_errors: [], futures_gap: 3,
  spot: { price: 4095, updated_at: at, age_seconds: 5, stale: false, price_source: 'x' },
  data_check: { ...agent('data', 'Data'), headline: 'Data fresh', veto: false, warnings: [] }, chief: chief(plan),
  agents: [
    agent('wyckoff', 'Wyckoff', { bias: 'BUY', levels: [{ kind: 'target', price: 4200, note: 'far target' }, { kind: 'entry', price: 4100 }] }),
    agent('sentiment', 'Market psychology', { metrics: { mood: 'GREED', greed: 2 }, rows: [['Mood', 'GREED'], ['Fear index', '61']], summary: 'The crowd is greedy.' }),
    agent('psychology', 'Discipline', { bias_label: 'CLEAR', headline: 'Fine', rows: [['Next big news', 'CPI in 2h']], warnings: [] }),
  ],
  track: { agents: { chief: { hits: 1, misses: 1, flat: 0, pending: 0, hit_rate: 50 } }, trades: { won: 1, lost: 0, open: 0, expired: 0, win_rate: 100, avg_r: 1, recent: [] } },
  weights_week: null,
})
const T0 = Math.floor(Date.now() / 900_000) * 900
const CALL = { side: 'BUY', kind: 'now', decided_t: T0 - 900, entry_t: T0 - 900, entry: 4091, stop: 4080, t1: 4116, exit_t: T0, exit: 4116, why: 'target', r: 2, usd: null, source: 'demo' }
const pts = (n: number, step: number) => Array.from({ length: n }, (_, i) => ({ t: T0 - (n - i) * step, o: 4090, h: 4096, l: 4085, c: 4090 + i * 0.1, v: 5 }))

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
let calls: { url: string; method: string }[]
let analyses: unknown[]
let futFail = false
function mockApi(over: Record<string, () => Response> = {}) {
  calls = []
  futFail = false
  analyses = [ANALYSIS()]
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? 'GET' })
    const path = url.split('?')[0]
    if (path in over) return over[path]()
    if (path === '/api/analysis') return json(analyses.length > 1 ? analyses.shift() : analyses[0])
    if (path === '/api/calls') return json({ days: 7, calls: [CALL] })
    if (path.endsWith('/intraday')) return json({ interval_seconds: 300, source: 'sampler', points: pts(40, 300).map((p) => ({ t: p.t, p: p.c })) })
    if (path.endsWith('/chart')) return futFail ? json({}, 500) : json({ points: pts(30, 900) })
    return new Response('{}', { status: 404 })
  }))
}
let client: QueryClient
function mount(path = '/trade') {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/trade" element={<TradePage />} />
            <Route path="/other" element={<div>another page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
const beep = vi.hoisted(() => ({ osc: 0 }))
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear(); beep.osc = 0
  vi.stubGlobal('AudioContext', class {
    currentTime = 0; destination = {}
    createOscillator() { beep.osc++; return { frequency: {}, connect() {}, start() {}, stop() {} } }
    createGain() { return { connect() {}, gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} } } }
  })
})
afterEach(() => {
  vi.unstubAllGlobals(); delete (window as { TradingView?: unknown }).TradingView; delete document.documentElement.dataset.theme
})

const srcBtn = (n: RegExp) => screen.getByRole('button', { name: n })
const isVisible = (el: HTMLElement | null) => { if (!el) return false; try { expect(el).toBeVisible(); return true } catch { return false } }
const charts = () => ['tv-chart', 'spot-chart', 'fut-chart'].filter((id) => isVisible(screen.queryByTestId(id)))

it('the source switch shows exactly one of the TradingView, Spot and Futures charts', async () => {
  mockApi()
  mount()
  expect(charts()).toEqual(['tv-chart'])
  fireEvent.click(srcBtn(/^Spot/))
  await waitFor(() => expect(charts()).toEqual(['spot-chart']))
  fireEvent.click(srcBtn(/^Futures/))
  await waitFor(() => expect(charts()).toEqual(['fut-chart']))
  fireEvent.click(srcBtn(/^TradingView/))
  await waitFor(() => expect(charts()).toEqual(['tv-chart']))
  expect(srcBtn(/^TradingView/)).toHaveAttribute('aria-pressed', 'true')
})

it('the Plan panel shows the Chief action and the entry, stop, 1R and target from the analysis', async () => {
  mockApi()
  mount()
  const d = await screen.findByRole('button', { name: /Chief analyst decision/ })
  expect(within(d).getByText('BUY NOW')).toBeInTheDocument()
  expect(within(d).getByText('Buy the dip')).toBeInTheDocument()
  const lv = (k: string) => within(d).getByText(k).parentElement!
  expect(lv('Entry')).toHaveTextContent('4,092.00')
  expect(lv('Entry')).toHaveTextContent('4,090.00 – 4,094.00')
  expect(lv('Stop loss')).toHaveTextContent('4,080.00')
  expect(lv('Stop loss')).toHaveTextContent('−$120 at 0.1 lot')
  expect(lv('Half off · 1R')).toHaveTextContent('4,104.00')
  expect(lv('Target')).toHaveTextContent('4,116.00')
  expect(lv('Target')).toHaveTextContent('+$240 · 2.0R')
  expect(d).toHaveTextContent('Size for $1,000 at 1% risk: 0.83 oz ≈ 0.01 lots')
  // the plan tab also carries the crowd card, discipline coach, timeframes, steps, vote, stop map, reasoning
  expect(screen.getByText('Market psychology · how the crowd is behaving')).toBeInTheDocument()
  expect(screen.getByText(/Discipline coach/)).toBeInTheDocument()
  expect(screen.getByText('Place a buy limit inside the zone')).toBeInTheDocument()
  expect(screen.getByText('Cancel: a 15m candle closes below 4085')).toBeInTheDocument()
  expect(screen.getByText(/Agent vote · 1 buy · 1 wait · 0 sell/)).toBeInTheDocument()
  expect(screen.getByText('Because trend is up.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Add this BUY NOW call to my journal/ })).toHaveAttribute('href', '/journal?call=1')
})

it('a WATCH plan shows the watch level and what to wait for instead of the level boxes', async () => {
  mockApi()
  const watch = { ...PLAN, kind: 'watch', action: 'WATCH', stop: null, be_at: null, t1: null, entry_lo: 4125, entry_hi: 4125, side: 'SELL' }
  analyses = [ANALYSIS(watch)]
  mount()
  const d = await screen.findByRole('button', { name: /Chief analyst decision/ })
  expect(within(d).getByText('Watch level · alert only')).toBeInTheDocument()
  expect(d).toHaveTextContent('Price spikes above 4,125.00')
  expect(within(d).queryByText('Stop loss')).not.toBeInTheDocument()
})

it('"Calls" requests /api/calls?days=7, then 30, then turns off; it moves the TradingView chart to Futures and marks the call', async () => {
  mockApi()
  mount()
  await screen.findByRole('button', { name: /Chief analyst decision/ })
  const btn = screen.getByRole('button', { name: /^Calls/ })
  fireEvent.click(btn)
  await waitFor(() => expect(calls.some((c) => c.url === '/api/calls?days=7')).toBe(true))
  await screen.findByTestId('fut-chart')
  expect(btn).toHaveTextContent('Calls 7d')
  await waitFor(() => expect(m.series.setMarkers.mock.calls.some(([mk]) => mk.some((x: { text: string }) => x.text === 'DEMO BUY 4,091.00'))).toBe(true))
  fireEvent.click(btn)
  await waitFor(() => expect(calls.some((c) => c.url === '/api/calls?days=30')).toBe(true))
  expect(btn).toHaveTextContent('Calls 30d')
  fireEvent.click(btn)
  expect(btn).toHaveTextContent(/^Calls$/)
  await waitFor(() => expect(m.series.setMarkers).toHaveBeenLastCalledWith([]))
})

it('the Spot chart draws the Chief levels (and Zones turns them off); the Futures chart draws none', async () => {
  mockApi()
  mount()
  await screen.findByRole('button', { name: /Chief analyst decision/ })
  fireEvent.click(srcBtn(/^Spot/))
  const titles = () => m.series.createPriceLine.mock.calls.map(([o]) => (o as { title: string }).title)
  await waitFor(() => expect(titles()).toEqual(expect.arrayContaining(['ENTRY', 'STOP', 'TARGET 1', 'HALF @1R', 'BUY STOPS', 'HUNTED'])))
  fireEvent.click(screen.getByLabelText('Zones'))
  await waitFor(() => expect(m.series.removePriceLine).toHaveBeenCalled())
  fireEvent.click(srcBtn(/^Futures/))
  await screen.findByTestId('fut-chart')
  expect(await screen.findByText(/Gold FUTURES \(COMEX\), not spot/)).toBeInTheDocument()
  expect(screen.getByText('Futures − spot: -2.10 $')).toBeInTheDocument() // last futures close 4092.9 − live 4095
})

it('spot timeframes that would hold fewer than 3 samples are disabled', async () => {
  mockApi()
  mount()
  fireEvent.click(srcBtn(/^Spot/))
  await screen.findByTestId('spot-chart')
  await waitFor(() => expect(screen.getByRole('button', { name: '5m' })).toBeDisabled())
  expect(screen.getByRole('button', { name: '1m' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '1d' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '15m' })).toBeEnabled()
  expect(screen.getByRole('button', { name: '15m' })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: '1h' }))
  expect(screen.getByRole('button', { name: '1h' })).toHaveAttribute('aria-pressed', 'true')
})

it('a failed candle request shows the message and no made-up candles', async () => {
  mockApi({ '/api/analysis': () => json(ANALYSIS()), 'https://xaus.com/api/v1/chart': () => json({}, 500) })
  mount()
  fireEvent.click(srcBtn(/^Futures/))
  expect(await screen.findByText(/Candles unavailable right now \(HTTP 500\)/)).toBeInTheDocument()
})

it('the decision banner opens the Chief details with the position-size calculator (keyboard)', async () => {
  mockApi()
  mount()
  const d = await screen.findByRole('button', { name: /Chief analyst decision/ })
  fireEvent.keyDown(d, { key: 'Enter' })
  const dlg = await screen.findByRole('dialog', { name: 'Chief analyst details' })
  expect(within(dlg).getByText('Stop-loss map')).toBeInTheDocument()
  expect(within(dlg).getByText('Track record')).toBeInTheDocument()
  expect(within(dlg).getByText(/\(reward 2× risk\)/)).toBeInTheDocument()
  fireEvent.change(within(dlg).getByLabelText('Account $'), { target: { value: '5000' } })
  fireEvent.change(within(dlg).getByLabelText('Risk %'), { target: { value: '2' } })
  expect(dlg).toHaveTextContent('Size for $5,000 at 2% risk: 8.33 oz ≈ 0.08 lots (lose about $100 if the stop is hit)')
  expect(localStorage.getItem('acct')).toBe('5000')
  expect(localStorage.getItem('riskPct')).toBe('2')
  fireEvent.keyDown(document, { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(d).toHaveTextContent('Size for $5,000 at 2% risk')
})

it('the Levels tab lists plan, stop-map and agent levels for today, and All levels adds the far ones', async () => {
  mockApi()
  mount()
  await screen.findByRole('button', { name: /Chief analyst decision/ })
  fireEvent.click(screen.getByRole('tab', { name: /Levels/ }))
  const tbl = await screen.findByRole('table', { name: 'Levels' })
  expect(within(tbl).getByText('4,116.00')).toBeInTheDocument()
  expect(within(tbl).queryByText('4,200.00')).not.toBeInTheDocument() // beyond one average day's move ($60)
  expect(tbl).toHaveTextContent('◀ current price')
  expect(screen.getByText(/1 far-away levels hidden/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'All levels' }))
  expect(within(screen.getByRole('table', { name: 'Levels' })).getByText('4,200.00')).toBeInTheDocument()
  expect(localStorage.getItem('lvMode')).toBe('all')
})

it('the discipline coach counts my trades and stops the day at the limit', async () => {
  mockApi()
  mount()
  await screen.findByRole('button', { name: /Chief analyst decision/ })
  const more = (what: string) => fireEvent.click(screen.getByRole('button', { name: `More ${what}` }))
  more('trades'); more('trades'); more('losses')
  expect(screen.getByText(/Your daily limit is reached/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Chief analyst decision/ })).toHaveTextContent('DONE FOR TODAY')
  expect(JSON.parse(localStorage.getItem('myDay')!)).toMatchObject({ trades: 2, losses: 1 })
})

it('a new NOW call raises the alert once; an unchanged call (even a later analysis) does not', async () => {
  localStorage.setItem('alerts', '1')
  mockApi()
  mount()
  expect(await screen.findByRole('alert')).toHaveTextContent('BUY NOW near 4,092.00 · stop 4,080.00 · half at 4,104.00 · target 4,116.00')
  expect(beep.osc).toBe(3)
  const refresh = screen.getByRole('button', { name: 'Refresh the analysis' })
  analyses = [ANALYSIS(PLAN, '2026-10-31T10:15:00Z')] // same plan, newer report
  fireEvent.click(refresh)
  await waitFor(() => expect(calls.some((c) => c.url === '/api/analysis?refresh=true')).toBe(true))
  await screen.findByText(/Updated .*/)
  await act(async () => { await new Promise((r) => setTimeout(r, 50)) })
  expect(beep.osc).toBe(3)
  analyses = [ANALYSIS({ ...PLAN, side: 'SELL', action: 'SELL NOW', entry_lo: 4150, entry_hi: 4154 }, '2026-10-31T10:30:00Z')]
  fireEvent.click(refresh)
  await waitFor(() => expect(beep.osc).toBe(6))
  expect(screen.getByRole('alert')).toHaveTextContent('SELL NOW near 4,152.00')
  expect(screen.getAllByRole('alert')).toHaveLength(1)
})

it('alerts stay silent while off; the bell turns them on (persisted) with a test pop-up', async () => {
  mockApi()
  mount()
  await screen.findByRole('button', { name: /Chief analyst decision/ })
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(beep.osc).toBe(0)
  const bell = screen.getByRole('button', { name: /Alerts for BUY NOW/ })
  expect(bell).toHaveAttribute('aria-pressed', 'false')
  fireEvent.click(bell)
  await waitFor(() => expect(bell).toHaveAttribute('aria-pressed', 'true'))
  expect(localStorage.getItem('alerts')).toBe('1')
  await waitFor(() => expect(beep.osc).toBeGreaterThanOrEqual(3))
  expect(await screen.findByRole('alert')).toBeInTheDocument()
})

it('the refresh button asks for ?refresh=true and "Next analysis" shows a countdown', async () => {
  mockApi()
  mount()
  await screen.findByRole('button', { name: /Chief analyst decision/ })
  expect(screen.getByText('Next analysis')).toHaveTextContent(/Next analysis\s*10:0\d|Next analysis\s*9:5\d/)
  fireEvent.click(screen.getByRole('button', { name: 'Refresh the analysis' }))
  await waitFor(() => expect(calls.some((c) => c.url === '/api/analysis?refresh=true' && c.method === 'GET')).toBe(true))
  expect(calls.some((c) => c.method !== 'GET')).toBe(false)
})

it('the bigger-chart button hides the analysis panel and brings it back', async () => {
  mockApi()
  mount()
  await screen.findByRole('button', { name: /Chief analyst decision/ })
  const big = screen.getByRole('button', { name: 'Bigger chart' })
  expect(screen.getByTestId('trade-panel')).not.toHaveClass('min-[900px]:hidden')
  fireEvent.click(big)
  expect(screen.getByTestId('trade-panel')).toHaveClass('min-[900px]:hidden')
  expect(big).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(big)
  expect(screen.getByTestId('trade-panel')).not.toHaveClass('min-[900px]:hidden')
})

it('the candle countdown pill shows the time left for the timeframe, and TradingView has its own picker', async () => {
  mockApi()
  mount()
  const tvPill = await screen.findByTestId('cd-pill')
  expect(tvPill).toHaveTextContent('15m')
  expect(tvPill).toHaveTextContent(/closes in\s*\d+:\d\d/)
  fireEvent.change(screen.getByLabelText('TradingView timeframe'), { target: { value: '1h' } })
  expect(screen.getByTestId('cd-pill')).toHaveTextContent('1h')
  fireEvent.click(srcBtn(/^Futures/))
  await screen.findByTestId('fut-chart')
  fireEvent.click(screen.getByRole('button', { name: '1d' }))
  await waitFor(() => expect(screen.queryByTestId('cd-pill')).not.toBeInTheDocument()) // daily candles: no countdown
})

/* ---- fix round 1 ---- */
const shift = () => -new Date().getTimezoneOffset() * 60
const lastBars = () => (m.series.setData.mock.calls.at(-1)![0] as { time: number; open: number; high: number; low: number; close: number }[])
  .map((b) => ({ ...b, time: b.time - shift() }))

it('live spot ticks accumulate: every candle survives and a bucket keeps its running high and low', async () => {
  mockApi()
  mount()
  fireEvent.click(srcBtn(/^Spot/))
  await screen.findByTestId('spot-chart')
  await waitFor(() => expect(m.series.setData.mock.calls.length).toBeGreaterThan(0))
  await waitFor(() => expect(lastBars().length).toBeGreaterThan(5))
  const n0 = lastBars().length
  act(() => m.setLive(4200, T0 + 10)) // opens the T0 candle
  act(() => m.setLive(4210, T0 + 910)) // opens the next one
  act(() => m.setLive(4150, T0 + 920)) // same bucket: low
  act(() => m.setLive(4230, T0 + 930)) // same bucket: high
  await waitFor(() => expect(lastBars()).toHaveLength(n0 + 2))
  const bars = lastBars()
  expect(bars.at(-2)).toMatchObject({ time: T0, open: 4200, high: 4200, low: 4200, close: 4200 })
  expect(bars.at(-1)).toMatchObject({ time: T0 + 900, open: 4210, high: 4230, low: 4150, close: 4230 })
})

it('NOW alerts fire on every page, not only while /trade is open', async () => {
  localStorage.setItem('alerts', '1')
  mockApi()
  mount('/other')
  expect(screen.getByText('another page')).toBeInTheDocument()
  expect(await screen.findByRole('alert')).toHaveTextContent('BUY NOW near 4,092.00')
  expect(beep.osc).toBe(3)
})

it('a theme change re-creates the TradingView widget with the new theme and clears a failed state', async () => {
  mockApi()
  mount()
  const holder = await screen.findByTestId('tv-chart')
  const bad = document.head.querySelector('script[src*="tradingview"]')!
  act(() => { bad.dispatchEvent(new Event('error')) })
  expect(await screen.findByText(/Could not load the TradingView chart/)).toBeInTheDocument()
  const widget = vi.fn()
  ;(window as unknown as { TradingView: unknown }).TradingView = { widget }
  fireEvent.click(screen.getByRole('button', { name: 'Toggle theme' }))
  await waitFor(() => expect(widget).toHaveBeenCalledTimes(1))
  expect(widget.mock.calls[0][0]).toMatchObject({ theme: 'light', symbol: 'OANDA:XAUUSD' })
  expect(screen.queryByText(/Could not load the TradingView chart/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Toggle theme' }))
  // a rebuild reloads tv.js like the old setTheme did; the widget is made once that script has loaded
  await waitFor(() => expect(document.head.querySelectorAll('script[src*="tradingview"]').length).toBeGreaterThan(0))
  act(() => { [...document.head.querySelectorAll('script[src*="tradingview"]')].at(-1)!.dispatchEvent(new Event('load')) })
  await waitFor(() => expect(widget).toHaveBeenCalledTimes(2))
  expect(widget.mock.calls[1][0]).toMatchObject({ theme: 'dark' })
  // switching to another source and back keeps the same widget (indicators and drawings survive)
  fireEvent.click(srcBtn(/^Spot/))
  await screen.findByTestId('spot-chart')
  expect(screen.getByTestId('tv-chart')).not.toBeVisible()
  expect(screen.getByTestId('tv-chart').closest('[aria-hidden="true"]')).not.toBeNull()
  fireEvent.click(srcBtn(/^TradingView/))
  expect(screen.getByTestId('tv-chart')).toBeVisible()
  expect(screen.getByTestId('tv-chart')).toBe(holder)
  expect(widget).toHaveBeenCalledTimes(2)
})

it('switching alerts on shows the test pop-up first and then the real NOW call', async () => {
  mockApi()
  mount()
  await screen.findByRole('button', { name: /Chief analyst decision/ })
  fireEvent.click(screen.getByRole('button', { name: /Alerts for BUY NOW/ }))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('BUY NOW near 4,092.00'))
  expect(screen.queryByText(/Alerts are on/)).not.toBeInTheDocument()
})

it('one failed 60 s futures poll keeps the candles and the label', async () => {
  mockApi()
  mount()
  fireEvent.click(srcBtn(/^Futures/))
  expect(await screen.findByText(/Gold FUTURES \(COMEX\), not spot/)).toBeInTheDocument()
  futFail = true
  await act(async () => { await client.refetchQueries({ queryKey: ['xaus', 'chart'] }) })
  expect(client.getQueryCache().findAll({ queryKey: ['xaus', 'chart'] })[0].state.status).toBe('error') // the poll really failed
  expect(screen.queryByText(/Candles unavailable/)).not.toBeInTheDocument()
  expect(screen.getByText(/Gold FUTURES \(COMEX\), not spot/)).toBeInTheDocument()
  expect(lastBars().length).toBe(30)
})

it('the daily-limit banner shows once the counters reach the limit even when a data veto already stops the plan', async () => {
  localStorage.setItem('myDay', JSON.stringify({ day: tradingDay(), trades: 2, losses: 0 }))
  mockApi()
  const a = ANALYSIS() as { data_check: { veto: boolean; warnings: string[] } }
  a.data_check = { ...a.data_check, veto: true, warnings: ['Price feed stale'] }
  analyses = [a]
  mount()
  const d = await screen.findByRole('button', { name: /Chief analyst decision/ })
  expect(d).toHaveTextContent('NO TRADE NOW')
  expect(screen.getByText(/Your daily limit is reached/)).toBeInTheDocument()
})

it('the entry level uses a theme token, not a hard-coded colour', async () => {
  mockApi()
  mount()
  const d = await screen.findByRole('button', { name: /Chief analyst decision/ })
  expect(within(d).getByText('Entry').nextElementSibling).toHaveClass('text-entry')
})

it('a call replay says the lot is assumed when the call carries none', async () => {
  mockApi()
  mount()
  await screen.findByRole('button', { name: /Chief analyst decision/ })
  fireEvent.click(screen.getByRole('button', { name: /^Calls/ }))
  await waitFor(() => expect(m.series.setMarkers.mock.calls.some(([mk]) => mk.length > 0)).toBe(true))
  act(() => { m.chart.subscribeClick.mock.calls.at(-1)![0]({ point: { x: 10, y: 10 } }) })
  const dlg = await screen.findByRole('dialog', { name: 'Trade replay' })
  expect(dlg).toHaveTextContent('assumed 0.1 lot')
})

/* ---- pure logic ---- */
it('aggregate groups samples into candles; withTick updates or opens the live bar', () => {
  const bars = aggregate([{ t: 0, p: 10 }, { t: 100, p: 12 }, { t: 400, p: 9 }, { t: 450, p: null }], 300)
  expect(bars).toEqual([
    { time: 0, open: 10, high: 12, low: 10, close: 12, volume: 0 },
    { time: 300, open: 9, high: 9, low: 9, close: 9, volume: 0 },
  ])
  expect(withTick(bars, 15, 350, 300)[1]).toMatchObject({ high: 15, close: 15, open: 9 })
  expect(withTick(bars, 15, 650, 300)).toHaveLength(3)
  expect(withTick(bars, 15, 10, 300)).toBe(bars) // older than the newest bar: ignored
  expect(bars[1].high).toBe(9) // input not mutated
})

it('fmtLeft counts down to the candle close; TF has the old table', () => {
  expect(fmtLeft(900, 900 * 10 + 899)).toBe('0:01')
  expect(fmtLeft(900, 900 * 10)).toBe('15:00')
  expect(fmtLeft(3600, 3600 * 5 + 61)).toBe('58:59')
  expect(fmtLeft(14400, 14400 * 3 + 1)).toBe('3:59:59')
  expect(TF['4h']).toMatchObject({ sec: 14400, fut: { interval: '1h', aggregate: true } })
})

it('sizeInfo and levelRows follow the old rules', () => {
  const s = sizeInfo({ ...PLAN } as never, 1000, 1)!
  expect(s.riskUsd).toBe(10)
  expect(s.oz).toBeCloseTo(10 / 12, 6)
  expect(sizeInfo({ ...PLAN, stop: null } as never, 1000, 1)).toBeNull()
  expect(sizeInfo({ ...PLAN } as never, 0, 1)).toBeNull()
  const a = ANALYSIS()
  const { rows } = levelRows(a.chief as never, a.agents as never, 4095, 'all')
  expect(rows.map((r) => r.price)).toEqual([...rows.map((r) => r.price)].sort((x, y) => y - x))
  expect(rows.find((r) => r.price === 4116)).toMatchObject({ kind: 'target', src: 'Chief plan', note: 'target 1' })
})

/* ---- change round 3: the chart toolbar lives in the header row ---- */
it('the source switch, timeframe, countdown and Calls sit in the same header as the title; no second toolbar row remains', async () => {
  mockApi()
  mount()
  const header = await screen.findByTestId('page-header')
  const h = within(header)
  expect(h.getByRole('heading', { name: 'Trade' })).toBeInTheDocument()
  expect(h.getByRole('group', { name: 'Chart source' })).toBeInTheDocument()
  expect(h.getByLabelText('TradingView timeframe')).toBeInTheDocument()
  expect(h.getByTestId('cd-pill')).toBeInTheDocument()
  expect(h.getByRole('button', { name: /^Calls/ })).toBeInTheDocument()
  expect(h.getByText('Next analysis')).toBeInTheDocument()
  expect(h.getByRole('button', { name: 'Refresh the analysis' })).toBeInTheDocument()
  const area = screen.getByTestId('chart-area')
  expect(within(area).queryByRole('group', { name: 'Chart source' })).not.toBeInTheDocument()
  expect(within(area).queryByTestId('cd-pill')).not.toBeInTheDocument()
  expect(within(area).getByLabelText('Zones')).toBeInTheDocument() // Zones stays reachable next to the chart
  fireEvent.click(srcBtn(/^Futures/))
  await screen.findByTestId('fut-chart')
  expect(within(header).getByRole('group', { name: 'Timeframe' })).toBeInTheDocument()
})

it('does not crash when the analysis payload is partial', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })))
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><TradePage /></MemoryRouter></QueryClientProvider>)
  expect(await screen.findByText(/Analysis unavailable/)).toBeInTheDocument()
})
