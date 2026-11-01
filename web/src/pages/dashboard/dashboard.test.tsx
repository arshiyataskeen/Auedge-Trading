import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { Demo, DemoTrade, JournalAccount, News } from '../../api/types'
import DashboardPage from './index'
import { Bar } from './Cards'

const m = vi.hoisted(() => ({ live: { price: 2005 as number | null, updatedAt: 1, source: 'x', status: 'live', change: null } }))
vi.mock('../../api/live', () => ({ useLivePrice: () => m.live }))

const NOW = Math.floor(Date.now() / 1000)
const check = (o: Record<string, unknown>) => ({
  rules: {}, status: 'active', breach: null, balance: 0, profit: 0, target_amt: null, target_left: null, days_traded: 0, min_days: 0,
  daily_limit: null, today_pnl: 0, daily_room: null, max_floor: null, max_room: null, equity: [], days: [], rr: {}, consistency: {}, stats: {}, ...o,
})
const acc = (o: Record<string, unknown>) => ({
  firm: '', size: 100000, created_at: 1, notes: '', archived: 0, phases: [], rules: { phases: [], funded: {}, reset: 'newyork', daily_base: 'initial' },
  total_phases: 2, n_trades: 0, last_trade_at: null, ...o,
}) as unknown as JournalAccount

const A = acc({
  id: 7, name: 'FTMO 100k', firm: 'FTMO', size: 100000, n_trades: 12, last_trade_at: 1793366100,
  rules: { phases: [{ name: 'Phase 1', max_loss_pct: 10 }, { name: 'Phase 2' }], funded: {}, reset: 'newyork', daily_base: 'initial' },
  current: { id: 1, name: 'Phase 1', is_funded: false, result: null, check: check({
    rules: { max_loss_pct: 10 }, balance: 101500, profit: 1500, target_amt: 10000, daily_limit: 5000, today_pnl: -120.5, daily_room: 4879.5,
    max_floor: 90000, max_room: 11500, days_traded: 3, min_days: 4,
  }) },
})
const B = acc({
  id: 8, name: 'Funded 50k', firm: 'Alpha', size: 50000, n_trades: 5, total_phases: 1,
  current: { id: 2, name: 'Funded', is_funded: true, result: null, check: check({
    status: 'breached', breach: { text: 'Daily loss limit broken' }, balance: 50300, profit: 300, today_pnl: 300, days_traded: 2,
  }) },
})
const D = acc({
  id: 9, name: 'AuEdge Demo', size: 25000, n_trades: 6,
  current: { id: 3, name: 'Demo test', is_funded: false, result: null, check: check({ today_pnl: 999 }) },
})
const ARCH = acc({
  id: 10, name: 'Old Acct', archived: 1, n_trades: 40,
  current: { id: 4, name: 'Phase 1', is_funded: false, result: null, check: check({ today_pnl: 5000 }) },
})

const open: DemoTrade = {
  id: 2, ts: NOW - 600, side: 'BUY', entry: 2000, stop: 1990, t1: 2020, gap: 0, lot: 0.1, cost: 0.3,
  status: 'open', half: 0, be: 2010, stop_now: 1990, unrealised: 0,
}
const demo = (o: Partial<Demo> = {}): Demo => ({
  start: 25000, lot: 0.1, balance: 25100, equity: 25100, realised: 100, today: -50, week: 200, trades: 6, wins: 5, win_rate: 83,
  open: [open], closed: [], curve: [], price: 2000, journal_account: 9, ...o,
})
const news = (events: Partial<News['events'][number]>[]): News => ({
  now: NOW, blocking: null,
  events: events.map((e) => ({ t: NOW + 7200, name: 'x', impact: 'High', forecast: '', previous: '', blocks: false, win_from: 0, win_to: 0, source: 'ff', ...e })),
})
const analysis = (plan: Record<string, unknown>) => ({
  next_in_s: 300,
  chief: { confidence: 72, headline: 'Gold leans up while above 2000', plan: { entry_lo: 1999, entry_hi: 2001, stop: 1990, be_at: 2010, t1: 2020, ...plan } },
})

const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200 })
let calls: string[]
function mockApi(over: Record<string, unknown> = {}) {
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(url)
    if (url in over) return json(over[url])
    const path = url.split('?')[0]
    if (path in over) return json(over[path])
    if (path === '/api/journal/accounts') return json({ accounts: url.includes('archived=true') ? [A, B, D, ARCH] : [A, B, D], now: NOW })
    if (path === '/api/demo') return json(demo())
    if (path === '/api/analysis') return json(analysis({ kind: 'now', side: 'BUY', action: 'BUY NOW' }))
    if (path === '/api/news') return json(news([{ name: 'Retail Sales', impact: 'Medium', t: NOW + 3600 }, { name: 'Non-Farm Payrolls', blocks: true }]))
    return new Response('{}', { status: 404 })
  }))
}
function mount() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><DashboardPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}
const stat = (label: string) => screen.getByText(label).previousElementSibling as HTMLElement

beforeEach(() => { m.live.price = 2005 })
afterEach(() => { vi.unstubAllGlobals() })

it('totals are computed from the real accounts and leave out the demo account', async () => {
  mockApi()
  mount()
  await screen.findByText('FTMO 100k')
  expect(stat('active accounts')).toHaveTextContent(/^2$/)
  expect(stat('funded')).toHaveTextContent(/^1$/)
  expect(stat('today, all accounts')).toHaveTextContent('+$180') // -120.5 + 300 = 179.5
  expect(stat('trades logged')).toHaveTextContent(/^17$/)
})

it('an account card links to its journal and shows the rule meters', async () => {
  mockApi()
  mount()
  const link = (await screen.findByText('FTMO 100k')).closest('a')!
  expect(link).toHaveAttribute('href', '/journal/7')
  expect(link).toHaveAccessibleName(/^Open FTMO 100k/)
  const c = within(link)
  expect(c.getByText('Phase 1 of 2')).toBeInTheDocument()
  expect(c.getByText('FTMO · $100,000 account')).toBeInTheDocument()
  expect(c.getByText('In progress')).toBeInTheDocument()
  expect(c.getByText('Profit target')).toBeInTheDocument()
  expect(c.getByText('of $10,000')).toBeInTheDocument()
  expect(c.getByText("Today's loss room")).toBeInTheDocument()
  expect(c.getByText('Max loss room')).toBeInTheDocument()
  expect(c.getByText('above $90,000')).toBeInTheDocument()
  expect(c.getByText(/12 trades · 3 of 4 trading days · last /)).toBeInTheDocument()
  const funded = screen.getByText('Funded 50k').closest('a')!
  expect(within(funded).getByText('Funded')).toBeInTheDocument()
  expect(within(funded).getByText('Rule broken')).toBeInTheDocument()
  expect(within(funded).getByText('Daily loss limit broken')).toBeInTheDocument()
  expect(within(funded).getByText('Profit so far')).toBeInTheDocument()
  expect(within(funded).getByText(/last none yet/)).toBeInTheDocument()
})

it('the demo card comes first, links to the demo journal and follows the live price', async () => {
  mockApi()
  mount()
  const link = await screen.findByLabelText("Open the AuEdge demo account's journal")
  expect(link).toHaveAttribute('href', '/journal/9')
  const all = screen.getAllByRole('link').map((l) => l.getAttribute('aria-label') ?? '')
  const demoAt = all.indexOf("Open the AuEdge demo account's journal")
  const ftmoAt = all.findIndex((l) => l.startsWith('Open FTMO 100k'))
  expect(demoAt).toBeGreaterThanOrEqual(0)
  expect(demoAt).toBeLessThan(ftmoAt)
  const c = within(link)
  expect(c.getByText('Trade open')).toBeInTheDocument()
  // BUY 0.1 lot from 2000, live 2005, cost 0.3 -> +$47; profit since start = 100 + 47
  expect(c.getByText('Open BUY 0.1').nextElementSibling).toHaveTextContent('+$47')
  expect(c.getByText('Profit since start').nextElementSibling).toHaveTextContent('+$147')
  expect(c.getByText('Automatic demo trading · $25,000 account · 0.1 lot')).toBeInTheDocument()
  expect(c.getByText('of $350')).toBeInTheDocument()
  expect(c.getByText(/6 closed trades · 83% won · last none yet · tap for its journal/)).toBeInTheDocument()
})

it('demo loss room shrinks with a losing day and the status changes at the limits', async () => {
  mockApi({ '/api/demo': demo({ open: [], today: -360 }) })
  mount()
  const link = await screen.findByLabelText("Open the AuEdge demo account's journal")
  expect(within(link).getByText('Day stopped (loss limit)')).toBeInTheDocument()
  expect(within(link).getByText("Today's loss room").nextElementSibling).toHaveTextContent('$0 of $350')
})

it('the today strip shows the call, demo position, today and the next big news', async () => {
  mockApi()
  mount()
  const call = (await screen.findByText('AuEdge call')).parentElement!
  expect(await within(call).findByText('BUY NOW')).toBeInTheDocument()
  expect(within(call).getByText(/confidence 72% · next in/)).toBeInTheDocument()
  expect(within(call).getByText('Entry 2,000.00 · stop 1,990.00 · half 2,010.00 · target 2,020.00')).toBeInTheDocument()
  expect(within(call).getByRole('link', { name: /Chart dashboard/ })).toHaveAttribute('href', '/trade')
  expect(within(call).getByRole('link', { name: /Add to my journal/ })).toBeInTheDocument()

  const pos = screen.getByText('AuEdge demo position').parentElement!
  expect(await within(pos).findByText('0.1 lot')).toBeInTheDocument()
  expect(within(pos).getByText('+$47')).toBeInTheDocument()
  expect(within(pos).getByText('Entry 2,000.00 · stop 1,990.00 · half 2,010.00 · target 2,020.00')).toBeInTheDocument()
  expect(within(pos).getByRole('link', { name: /Open the Demo tab/ })).toHaveAttribute('href', '/demo')

  const today = screen.getByText('Today').parentElement!
  expect(within(today).getByText('−$50')).toBeInTheDocument()
  expect(today).toHaveTextContent('AuEdge demo · this week +$200')
  expect(today).toHaveTextContent('Journal accounts +$180')

  const nw = screen.getByText('Next big news').parentElement!
  expect(await within(nw).findByText('Non-Farm Payrolls')).toBeInTheDocument() // High only, not the Medium one
  expect(within(nw).getByText(/in 1h 59m|in 2h 0m/)).toBeInTheDocument()
  expect(within(nw).getByText(/no new trades around it/)).toBeInTheDocument()
})

it('a watch call shows the headline and no journal button; no news and no demo trade have their own text', async () => {
  mockApi({
    '/api/analysis': analysis({ kind: 'watch', side: null, action: 'WATCH' }),
    '/api/news': news([{ impact: 'Medium' }]), '/api/demo': demo({ open: [] }),
  })
  mount()
  const call = (await screen.findByText('AuEdge call')).parentElement!
  expect(await within(call).findByText('WATCH')).toBeInTheDocument()
  expect(within(call).getByText('Gold leans up while above 2000')).toBeInTheDocument()
  expect(within(call).queryByRole('link', { name: /Add to my journal/ })).not.toBeInTheDocument()
  expect(await screen.findByText('No open trade')).toBeInTheDocument()
  expect(screen.getByText('Balance $25,100 · 6 closed trade(s) · waiting for the next BUY / SELL NOW call.')).toBeInTheDocument()
  expect(await screen.findByText('No high-impact US news coming up.')).toBeInTheDocument()
})

it('the archived toggle reloads with archived=true but archived accounts stay out of the totals', async () => {
  mockApi()
  mount()
  await screen.findByText('FTMO 100k')
  fireEvent.click(screen.getByRole('button', { name: 'Show archived accounts' }))
  expect(await screen.findByText('Old Acct')).toBeInTheDocument()
  expect(calls).toContain('/api/journal/accounts?archived=true')
  expect(stat('active accounts')).toHaveTextContent(/^2$/)
  expect(stat('trades logged')).toHaveTextContent(/^17$/)
  fireEvent.click(screen.getByRole('button', { name: 'Hide archived accounts' }))
  await waitFor(() => expect(screen.queryByText('Old Acct')).not.toBeInTheDocument())
})

it('with no real accounts it invites adding one; header links go to the journal', async () => {
  mockApi({ '/api/journal/accounts': { accounts: [D], now: NOW } })
  mount()
  expect(await screen.findByText('＋ Add your prop-firm account')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'All records' })).toHaveAttribute('href', '/journal')
  expect(screen.getByText('Tips')).toBeInTheDocument()
})

it('the toggle and the today strip stay mounted while archived loads and after a failed archived fetch', async () => {
  mockApi()
  mount()
  await screen.findByText('FTMO 100k')
  let release!: () => void
  const gate = new Promise<void>((r) => { release = r })
  const base = globalThis.fetch as unknown as (u: string) => Promise<Response>
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/journal/accounts?archived=true') { await gate; return new Response('{"error":"boom"}', { status: 500 }) }
    return base(url)
  }))
  fireEvent.click(screen.getByRole('button', { name: 'Show archived accounts' }))
  // during the refetch: no loading placeholder, previous cards and the toggle remain
  expect(screen.getByRole('button', { name: /archived accounts/ })).toBeInTheDocument()
  expect(screen.queryByTestId('loading-card')).not.toBeInTheDocument()
  expect(screen.getByText('FTMO 100k')).toBeInTheDocument()
  release()
  await screen.findByRole('alert')
  expect(screen.getByRole('button', { name: 'Hide archived accounts' })).toBeInTheDocument()
  expect(screen.getByText('AuEdge call')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Hide archived accounts' }))
  expect(await screen.findByText('FTMO 100k')).toBeInTheDocument()
})

it('an accounts error does not hide the today strip', async () => {
  mockApi()
  const base = globalThis.fetch as unknown as (u: string) => Promise<Response>
  vi.stubGlobal('fetch', vi.fn(async (url: string) =>
    url.startsWith('/api/journal/accounts') ? new Response('{"error":"x"}', { status: 500 }) : base(url)))
  mount()
  await screen.findByRole('alert')
  expect(screen.getByText('AuEdge call')).toBeInTheDocument()
  expect(await screen.findByText('Non-Farm Payrolls')).toBeInTheDocument()
})

it('totals and cards wait for the demo query, so the demo account never flashes in', async () => {
  mockApi()
  let release!: () => void
  const gate = new Promise<void>((r) => { release = r })
  const base = globalThis.fetch as unknown as (u: string) => Promise<Response>
  vi.stubGlobal('fetch', vi.fn(async (url: string) => { if (url === '/api/demo') await gate; return base(url) }))
  mount()
  await waitFor(() => expect(calls).toContain('/api/journal/accounts'))
  await new Promise((r) => setTimeout(r, 50))
  expect(screen.queryByText('AuEdge Demo', { selector: 'b' })).not.toBeInTheDocument()
  expect(stat('active accounts')).toHaveTextContent('—')
  release()
  await screen.findByText('FTMO 100k')
  expect(stat('active accounts')).toHaveTextContent(/^2$/)
})

it('if /api/demo fails the page still renders the old way', async () => {
  mockApi({ '/api/demo': undefined })
  const base = globalThis.fetch as unknown as (u: string) => Promise<Response>
  vi.stubGlobal('fetch', vi.fn(async (url: string) => (url === '/api/demo' ? new Response('{}', { status: 500 }) : base(url))))
  mount()
  expect(await screen.findByText('FTMO 100k')).toBeInTheDocument()
})

it('the empty-state card is its own grid item beside the demo card, dashed; the demo card is accent-bordered', async () => {
  mockApi({ '/api/journal/accounts': { accounts: [D], now: NOW } })
  mount()
  const add = (await screen.findByText('＋ Add your prop-firm account')).closest('a')!
  const demoCard = screen.getByLabelText("Open the AuEdge demo account's journal")
  expect(add.parentElement).toBe(demoCard.parentElement)
  expect(add.className).toMatch(/border-dashed/)
  expect(demoCard.className).toMatch(/border-up/)
})

it('the today strip is a 2-column grid under 1100 px and one column on phones', async () => {
  mockApi()
  mount()
  const strip = await screen.findByTestId('today-strip')
  expect(strip.className).toMatch(/grid-cols-1/)
  expect(strip.className).toMatch(/min-\[640px\]:grid-cols-2/)
  expect(strip.className).toMatch(/min-\[1100px\]:grid-cols-\[1\.3fr_1\.3fr_0\.9fr_1fr\]/)
})

it('the room meter fill uses the entry colour token', () => {
  const { container } = render(<Bar pct={40} cls="room" />)
  expect(container.querySelector('span')).toHaveClass('bg-entry')
})
