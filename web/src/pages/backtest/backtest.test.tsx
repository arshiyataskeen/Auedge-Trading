import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import fixture from './fixture.json'
import BacktestPage from './index'

const m = vi.hoisted(() => {
  const series = { setData: vi.fn(), setMarkers: vi.fn(), createPriceLine: vi.fn() }
  const chart = {
    addCandlestickSeries: vi.fn(() => series), remove: vi.fn(),
    timeScale: vi.fn(() => ({ setVisibleLogicalRange: vi.fn() })),
  }
  return { createChart: vi.fn(() => chart) }
})
vi.mock('lightweight-charts', () => ({
  createChart: m.createChart, CrosshairMode: { Normal: 0 }, LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
}))

const ID = 'bt_20261031_210229'
const OLD = 'bt_20261030_223755'
const LAST = 1793393100
const run = (id: string) => ({ ...fixture.params, id, made_at: 1, n: 10, win_rate: 70, total_r: 3, total_usd: 679.88 })
const info = {
  range: { first_1h: 1779361200, first_15m: 1790423100, last: LAST, cached: true },
  runs: [run(ID), run(OLD)],
}
const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200 })

let calls: { url: string; init?: RequestInit }[]
function mockApi(over: Record<string, unknown> = {}) {
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const path = url.split('?')[0]
    if (url in over) return json(over[url]); if (path in over) return json(over[path])
    if (path === '/api/backtest/info') return json(info)
    if (path === '/api/backtest/status') return json({ running: false })
    if (path === '/api/health/latest') return json({ error: 'none' })
    if (path.startsWith('/api/backtest/result/')) return json(fixture)
    if (path === '/api/backtest/candles') return json({ tf: '15m', sec: 900, candles: [] })
    if (path === '/api/backtest/run') return json({ ok: true, id: 'bt_new' })
    return new Response('{}', { status: 404 })
  }))
}

function mount() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><BacktestPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => { vi.clearAllMocks(); localStorage.clear() })
afterEach(() => { vi.unstubAllGlobals() })

it('opens the newest run', async () => {
  mockApi()
  mount()
  expect(await screen.findByText('Ending balance')).toBeInTheDocument()
  expect(screen.getByText('$25,680')).toBeInTheDocument()
  expect(screen.getByText('Biggest drop from a high:', { exact: false })).toBeInTheDocument()
  expect(calls.some((c) => c.url === `/api/backtest/result/${ID}`)).toBe(true)
  expect(screen.getByLabelText('Saved runs')).toHaveValue(ID)
  // New-backtest and Health-check panels stay closed until clicked
  expect(screen.queryByText('Choose a period to test')).not.toBeInTheDocument()
})

it('switching the run picker opens that run', async () => {
  mockApi()
  mount()
  await screen.findByText('Ending balance')
  fireEvent.change(screen.getByLabelText('Saved runs'), { target: { value: OLD } })
  await waitFor(() => expect(calls.some((c) => c.url === `/api/backtest/result/${OLD}`)).toBe(true))
})

it('clicking a month shows its calendar under the table and stays on Months', async () => {
  mockApi()
  mount()
  await screen.findByText('Ending balance')
  expect(screen.queryByTestId('calgrid')).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('July 2026'))
  const grid = await screen.findByTestId('calgrid')
  const table = screen.getByRole('table')
  expect(table.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.getByRole('tab', { name: 'Months' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getAllByRole('tabpanel')).toHaveLength(1)
})

it('clicking a day lists its trades; clicking a trade opens the replay with src=backup', async () => {
  mockApi()
  mount()
  await screen.findByText('Ending balance')
  fireEvent.click(screen.getByText('July 2026'))
  const days = (await screen.findAllByTestId('cal-day')).filter((d) => !(d as HTMLButtonElement).disabled)
  expect(days).toHaveLength(5)
  expect(screen.queryAllByTitle('Click to replay')).toHaveLength(0)
  fireEvent.click(days[0])
  const rows = await screen.findAllByTitle('Click to replay')
  expect(rows).toHaveLength(1)
  fireEvent.click(rows[0])
  expect(await screen.findByRole('dialog', { name: 'Trade replay' })).toBeInTheDocument()
  await waitFor(() => expect(calls.some((c) => c.url.startsWith('/api/backtest/candles?') && c.url.includes('&src=backup'))).toBe(true))
})

it('Trades tab lists newest first and Details tab shows the rules used', async () => {
  mockApi()
  mount()
  await screen.findByText('Ending balance')
  fireEvent.click(screen.getByRole('tab', { name: 'Trades' }))
  const rows = await screen.findAllByTitle('Click to replay')
  expect(rows).toHaveLength(10)
  expect(rows[0].getAttribute('data-ti')).toBe('9')
  fireEvent.click(screen.getByRole('tab', { name: 'Details' }))
  expect(await screen.findByText('Agents: 4-hour direction right?')).toBeInTheDocument()
})

it('New backtest posts the same body fields as the old UI', async () => {
  mockApi()
  mount()
  await screen.findByText('Ending balance')
  fireEvent.click(screen.getByRole('button', { name: /New backtest/ }))
  expect(await screen.findByText('Choose a period to test')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Run backtest' }))
  await waitFor(() => expect(calls.some((c) => c.url === '/api/backtest/run')).toBe(true))
  const post = calls.find((c) => c.url === '/api/backtest/run')!
  expect(post.init?.method).toBe('POST')
  const to = new Date(LAST * 1000).toISOString().slice(0, 10)
  const from = new Date(Date.parse(to) - 29 * 864e5).toISOString().slice(0, 10)
  expect(JSON.parse(post.init!.body as string)).toEqual({
    start: from, end: to, step: 'auto', spread: 0.3, account: 25000, lot: 0.1, target_rr: null, partial: true,
    adaptive: false, day_max_loss: 350, day_max_profit: 150, live_rules: true, f_session: false, f_trend: false, f_hunt: false,
  })
  expect(localStorage.getItem('btDayLoss')).toBe('350')
})

it('Harsh costs doubles the cost per side and adds stop slippage; target R:R is sent as a number', async () => {
  mockApi()
  mount()
  await screen.findByText('Ending balance')
  fireEvent.click(screen.getByRole('button', { name: /New backtest/ }))
  fireEvent.click(await screen.findByLabelText('Harsh costs'))
  fireEvent.change(screen.getByLabelText('Target R:R'), { target: { value: '2.5' } })
  fireEvent.click(screen.getByRole('button', { name: 'Run backtest' }))
  await waitFor(() => expect(calls.some((c) => c.url === '/api/backtest/run')).toBe(true))
  const body = JSON.parse(calls.find((c) => c.url === '/api/backtest/run')!.init!.body as string)
  expect(body).toMatchObject({ spread: 0.6, stop_slip: 0.5, target_rr: 2.5 })
})

it('shows the server error text when a run is refused', async () => {
  mockApi({ '/api/backtest/run': { ok: false, error: 'A run is already in progress' } })
  mount()
  await screen.findByText('Ending balance')
  fireEvent.click(screen.getByRole('button', { name: /New backtest/ }))
  fireEvent.click(await screen.findByRole('button', { name: 'Run backtest' }))
  expect(await screen.findByText('A run is already in progress')).toBeInTheDocument()
})

it('Health check opens below the header and posts the chosen period', async () => {
  mockApi()
  mount()
  await screen.findByText('Ending balance')
  fireEvent.click(screen.getByRole('button', { name: 'Health check' }))
  fireEvent.click(await screen.findByRole('button', { name: /Run health check/ }))
  await waitFor(() => expect(calls.some((c) => c.url === '/api/health/run')).toBe(true))
  expect(JSON.parse(calls.find((c) => c.url === '/api/health/run')!.init!.body as string)).toEqual({ period: 'month' })
})

it('shows a progress bar while a run is active', async () => {
  mockApi({ '/api/backtest/status': { running: true, id: 'bt_new', progress: { done: 30, total: 100, phase: 'Replaying' }, elapsed: 12 } })
  mount()
  await screen.findByText('Ending balance')
  fireEvent.click(screen.getByRole('button', { name: /New backtest/ }))
  const bar = await screen.findByRole('progressbar')
  expect(bar).toHaveAttribute('aria-valuenow', '30')
  expect(within(bar.parentElement!).getByText(/Replaying · 30%/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Run backtest' })).toBeDisabled()
})

it('calendar tints winning days up-bg and losing days down-bg', async () => {
  mockApi()
  mount()
  await screen.findByText('Ending balance')
  fireEvent.click(screen.getByText('July 2026'))
  const days = (await screen.findAllByTestId('cal-day')).filter((d) => !(d as HTMLButtonElement).disabled)
  expect(days.some((d) => d.className.includes('bg-up-bg'))).toBe(true)
  expect(days.some((d) => d.className.includes('bg-down-bg'))).toBe(true)
})

it('Trades rows open the replay from a real button (keyboard)', async () => {
  mockApi()
  mount()
  await screen.findByText('Ending balance')
  fireEvent.click(screen.getByRole('tab', { name: 'Trades' }))
  const btns = await screen.findAllByRole('button', { name: /Replay trade closed/ })
  expect(btns).toHaveLength(10)
  btns[0].focus()
  expect(btns[0]).toHaveFocus()
  fireEvent.keyDown(btns[0], { key: 'Enter' })
  fireEvent.click(btns[0]) // a browser turns Enter on a focused button into a click
  expect(await screen.findByRole('dialog', { name: 'Trade replay' })).toBeInTheDocument()
})

it('By year rows select the year from a real button', async () => {
  const two = { ...fixture, trades: [...fixture.trades, { ...fixture.trades[9], exit_t: 1815000000, usd: 50, balance: 1 }] }
  mockApi({ [`/api/backtest/result/${ID}`]: two })
  mount()
  await screen.findByText('Ending balance')
  const b = await screen.findByRole('button', { name: 'Show 2027' })
  b.focus()
  fireEvent.click(b)
  expect(await screen.findByText('2027 total')).toBeInTheDocument()
})
