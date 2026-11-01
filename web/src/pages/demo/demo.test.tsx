import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { Demo, DemoTrade } from '../../api/types'
import DemoPage from './index'
import DemoCalendarPage from './Calendar'
import { money } from '../../lib/format'
import { demoPnl, demoToTrade } from './logic'

const m = vi.hoisted(() => {
  const series = { setData: vi.fn(), setMarkers: vi.fn(), createPriceLine: vi.fn() }
  const chart = {
    addCandlestickSeries: vi.fn(() => series), remove: vi.fn(),
    timeScale: vi.fn(() => ({ setVisibleLogicalRange: vi.fn() })),
  }
  return { live: { price: 2000 as number | null, updatedAt: 1, source: 'x', status: 'live', change: null }, createChart: vi.fn(() => chart) }
})
vi.mock('lightweight-charts', () => ({
  createChart: m.createChart, CrosshairMode: { Normal: 0 }, LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
}))
vi.mock('../../api/live', () => ({ useLivePrice: () => m.live }))

const T0 = Math.floor(new Date(2026, 5, 2, 10).getTime() / 1000)
const open: DemoTrade = {
  id: 2, ts: T0, side: 'BUY', entry: 2000, stop: 1990, t1: 2020, gap: 0, lot: 0.1, cost: 0.3,
  status: 'open', half: 0, be: 2010, stop_now: 1990, unrealised: 0,
}
const closed: DemoTrade = {
  id: 1, ts: T0 - 86400, side: 'SELL', entry: 2010, stop: 2020, t1: 1990, gap: 12.5, lot: 0.1, cost: 0.3,
  status: 'target', half: 1, be: 2000, closed_ts: T0 - 86400 + 3600, exit_price: 1990, usd: 150, why: 'target', result_r: 2,
}
const demo: Demo = {
  start: 25000, lot: 0.1, balance: 25150, equity: 25150, realised: 150, today: 0, week: 150, trades: 1, wins: 1, win_rate: 100,
  open: [open], closed: [closed], curve: [[T0, 150]], price: 2000, journal_account: 1,
}
const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200 })
const TZ = new Date().getTimezoneOffset()

let calls: string[]
let current: Demo = demo
function mockApi() {
  calls = []
  current = demo
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(url)
    const path = url.split('?')[0]
    if (path === '/api/demo') return json(current)
    if (path === '/api/calendar') {
      return json({ days: {
        '2026-05-30': { pnl: -40, trades: 1, nows: 1, live: true, sim: false },
        '2026-06-02': { pnl: 150, trades: 2, nows: 2, live: false, sim: true },
      } })
    }
    if (path === '/api/calendar/day') {
      return json({
        date: '2026-06-02', source: 'live', steps: 4, nows: 2, pnl: 150, window: [T0 - 3600, T0 + 86400], timeline: [], agents: {}, trades: [],
        levels: { start: null, end: null },
      })
    }
    if (path === '/api/backtest/candles') return json({ tf: '15m', sec: 900, candles: [{ t: T0, o: 2000, h: 2005, l: 1995, c: 2001 }] })
    return new Response('{}', { status: 404 })
  }))
}

function tree(at: string, qc: QueryClient) {
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/demo" element={<DemoPage />} />
          <Route path="/demo/calendar" element={<DemoCalendarPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}
const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } })
function mount(at: string) {
  const qc = newClient()
  return { qc, ...render(tree(at, qc)) }
}

beforeEach(() => { vi.clearAllMocks(); m.live.price = 2000; mockApi() })
afterEach(() => { vi.unstubAllGlobals() })

it('demoPnl mirrors core/track.py: rest marked to price, half closed at 1R', () => {
  expect(demoPnl({ ...open }, 2005)).toBe(47)
  expect(demoPnl({ ...open, half: 1 }, 2005)).toBeCloseTo(0.5 * (2010 - 0.3 - 2000) * 10 + 0.5 * 47, 2)
  expect(demoPnl({ ...open, side: 'SELL', entry: 2000, stop: 2010, be: 1990 }, 1995)).toBe(Math.round((2000 - 1995 - 0.3) * 10 * 100) / 100)
})

it('demoToTrade keeps gap, lot and open state', () => {
  const t = demoToTrade({ ...open, unrealised: 12 })
  expect(t).toMatchObject({ kind: 'now', open: true, usd: 12, why: 'open', gap: 0, lot: 0.1 })
  expect(demoToTrade(closed)).toMatchObject({ open: false, usd: 150, gap: 12.5, exit: 1990, why: 'target' })
})

it('open position P&L follows the live price', async () => {
  const { rerender, qc } = mount('/demo')
  const pnl = await screen.findByTestId('open-pnl')
  expect(pnl).toHaveTextContent(money(demoPnl(open, 2000)))
  m.live.price = 2005
  rerender(tree('/demo', qc))
  await waitFor(() => expect(screen.getByTestId('open-pnl')).toHaveTextContent('+$47'))
  expect(screen.getByTestId('open-pnl')).toHaveTextContent(money(demoPnl(open, 2005)))
  // balance card follows too: balance + unrealised
  expect(screen.getByTestId('demo-equity')).toHaveTextContent('$25,197')
})

it('clicking a closed trade opens the replay with its gap', async () => {
  mount('/demo')
  const row = await screen.findByRole('button', { name: /replay.*SELL/i })
  fireEvent.click(row)
  const dlg = await screen.findByRole('dialog', { name: 'Trade replay' })
  expect(within(dlg).getByText(/shifted to spot \(−\$12\.50/)).toBeInTheDocument()
  await waitFor(() => expect(calls.some((u) => u.startsWith('/api/backtest/candles?'))).toBe(true))
})

it('calendar day click requests /api/calendar/day with date and tz offset', async () => {
  mount('/demo/calendar')
  expect(await screen.findByText(/June 2026/)).toBeInTheDocument()
  expect(calls).toContain(`/api/calendar?tz=${TZ}`)
  fireEvent.click(screen.getByRole('button', { name: /2026-06-02/ }))
  await waitFor(() => expect(calls).toContain(`/api/calendar/day?date=2026-06-02&tz=${TZ}`))
  expect(await screen.findByText('Replay the whole day', { exact: false })).toBeInTheDocument()
})

it('days without data are disabled and the month arrows move the month', async () => {
  mount('/demo/calendar')
  await screen.findByText(/June 2026/)
  expect(screen.getByRole('button', { name: '2026-06-03' })).toBeDisabled()
  fireEvent.click(screen.getByLabelText('Previous month'))
  expect(screen.getByText(/May 2026/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /2026-05-30/ })).toBeEnabled()
})

it('an open replay stays on the same trade after a refetch adds a newer closed trade', async () => {
  const { qc } = mount('/demo')
  fireEvent.click(await screen.findByRole('button', { name: /replay.*SELL/i }))
  const dlg = await screen.findByRole('dialog', { name: 'Trade replay' })
  expect(within(dlg).getByText(/shifted to spot \(−\$12\.50/)).toBeInTheDocument()
  const newer: DemoTrade = { ...closed, id: 9, ts: T0 + 100, side: 'BUY', gap: 0, entry: 2001, exit_price: 2011, usd: 10 }
  current = { ...demo, closed: [newer, closed], trades: 2 }
  await qc.invalidateQueries()
  await waitFor(() => expect(screen.getAllByRole('button', { name: /replay/i })).toHaveLength(2))
  expect(within(screen.getByRole('dialog', { name: 'Trade replay' })).getByText(/shifted to spot \(−\$12\.50/)).toBeInTheDocument()
})
