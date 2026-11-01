import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import JournalPage from './index'
import JournalAccountPage from './Account'
import { CSV_COLS, csvText, readImage } from './logic'

const NOW = Math.floor(Date.now() / 1000)
const stats = { n: 2, open: 0, wins: 1, losses: 1, win_rate: 50, avg_win: 100, avg_loss: -50, profit_factor: 2, best: 100, worst: -50, avg_r: 0.5,
  followed_plan_pct: null, followed_pnl: null, broke_pnl: null, by_setup: [], by_emotion: [] }
const check = (o: Record<string, unknown> = {}) => ({
  rules: { target_pct: 10, daily_loss_pct: 5, max_loss_pct: 10, max_loss_type: 'static', min_days: 4 }, status: 'active', breach: null,
  balance: 10050, profit: 50, target_amt: 1000, target_left: 950, days_traded: 2, min_days: 4, daily_limit: 500, today_pnl: 0, daily_room: 500,
  max_floor: 9000, max_room: 1050, equity: [[1, 100], [2, 50]], days: [{ day: '2026-10-30', pnl: 100, n: 1 }, { day: '2026-10-31', pnl: -50, n: 1 }],
  rr: { n_with_stop: 0, n_without_stop: 0, avg_planned: null, avg_achieved: null, avg_win_r: null, avg_loss_r: null, breakeven_win_rate: null,
    win_rate: null, expectancy_usd: null, expectancy_r: null, hit_target: 0, with_target: 0, dist: [] },
  consistency: { limit_pct: null, best_day: null, best_day_share: null, ok: null, profit_needed: null, win_days: 1, loss_days: 1, avg_win_day: 100,
    avg_loss_day: -50, worst_day: -50, biggest_trade_share: null, avg_lots: null, max_lots: null, min_lots: null, lot_spread: null },
  stats, ...o,
})
const phase = (id: number, idx: number, o: Record<string, unknown> = {}) => ({
  id, account_id: 5, idx, name: idx === 0 ? 'Phase 1' : idx === 1 ? 'Phase 2' : 'Funded', start_balance: 10000, started_at: 1790000000,
  ended_at: null, result: null, note: null, is_funded: idx === 2, check: check(), ...o,
})
const trade = (id: number, o: Record<string, unknown> = {}) => ({
  id, account_id: 5, phase_id: 1, opened_at: 1793300000 + id, closed_at: 1793303600, side: 'BUY', symbol: 'XAUUSD', lots: 0.1, entry: 2000, stop: 1990,
  target: 2020, exit: 2010, pnl: 100, commission: 0, setup: 'Breakout', source: 'manual', auedge: null, emotion: 'Calm', followed_plan: 1,
  mistakes: '', notes: 'Clean "one"', rating: 4, image: null, created_at: 1, net: 100, r: 1, planned_rr: 2, day: '2026-10-30',
  account: 'FTMO 10k', account_size: 10000, archived: 0, phase: 'Phase 1', phase_idx: 0, ...o,
})
const rules = { phases: [{ name: 'Phase 1' }, { name: 'Phase 2' }], funded: {}, reset: 'utc', daily_base: 'initial' }
const accOf = (phases: ReturnType<typeof phase>[], o: Record<string, unknown> = {}) => ({
  id: 5, name: 'FTMO 10k', firm: 'FTMO', size: 10000, created_at: 1790000000, rules, notes: '', archived: 0, phases,
  current: phases.find((p) => !p.result) ?? null, total_phases: 3, n_trades: 2, last_trade_at: 1793303600, ...o,
})
const ACC = accOf([phase(1, 0)])
const T1 = trade(11), T2 = trade(12, { side: 'SELL', net: -50, r: -0.5, setup: 'London sweep', emotion: 'FOMO', day: '2026-10-31', notes: 'revenge' })

type Call = { url: string; method: string; body: unknown }
let calls: Call[]
const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200 })
function mockApi(over: Record<string, (body: unknown) => unknown> = {}, detail: unknown = { ...ACC, trades: [T1, T2] }) {
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ url, method, body })
    const key = `${method} ${url.split('?')[0]}`
    if (key in over) return json(over[key](body))
    if (key === 'GET /api/journal/accounts') return json({ accounts: [ACC], now: NOW })
    if (key === 'GET /api/journal/accounts/5') return json(detail)
    if (key === 'GET /api/journal/trades') return json({ trades: [T1, T2] })
    if (key === 'GET /api/demo') return json({ journal_account: 2 })
    if (key === 'GET /api/analysis') return json({
      next_in_s: 300, generated_at: '2026-11-01T10:00:00Z',
      chief: { confidence: 72, plan: { kind: 'now', side: 'SELL', action: 'SELL NOW', entry_lo: 1999.5, entry_hi: 2000.5, stop: 2010, be_at: 1990, t1: 1970 } },
    })
    if (method !== 'GET') return json({ ok: true, id: 9 })
    return new Response('{}', { status: 404 })
  }))
}
const posted = (method: string, url: string) => calls.find((c) => c.method === method && c.url === url)

function Where() { const l = useLocation(); return <div data-testid="where">{l.pathname + l.search}</div> }
function mount(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Where />
        <Routes>
          <Route path="/journal" element={<JournalPage />} />
          <Route path="/journal/:accountId" element={<JournalAccountPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

const typeInto = (label: string | RegExp, v: string) => {
  const dlg = screen.getByRole('dialog')
  fireEvent.change(within(dlg).getByLabelText(label), { target: { value: v } })
}

it('?new=1 opens the new-account form and clears the parameter', async () => {
  mockApi()
  mount('/journal?new=1')
  expect(await screen.findByRole('dialog', { name: 'New prop-firm account' })).toBeInTheDocument()
  expect(screen.getByTestId('where')).toHaveTextContent(/^\/journal$/)
})

it('the "Common 2-step" preset posts the same JSON as the old readRules()', async () => {
  mockApi()
  mount('/journal?new=1')
  await screen.findByRole('dialog')
  typeInto('Name', '10K Challenge #1')
  typeInto('Firm', 'FTMO')
  typeInto(/Account size/, '10000')
  fireEvent.click(screen.getByRole('button', { name: 'Common 2-step' }))
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
  await waitFor(() => expect(posted('POST', '/api/journal/accounts')).toBeTruthy())
  const ph = (name: string, target: string) => ({ name, target_pct: target, daily_loss_pct: '5', max_loss_pct: '10', max_loss_type: 'static', min_days: '4', consistency_pct: '' })
  expect(posted('POST', '/api/journal/accounts')!.body).toEqual({
    name: '10K Challenge #1', firm: 'FTMO', size: 10000, notes: '',
    rules: { phases: [ph('Phase 1', '10'), ph('Phase 2', '5')],
      funded: { daily_loss_pct: '5', max_loss_pct: '10', max_loss_type: 'static', profit_split: '80', consistency_pct: '' },
      reset: 'utc', daily_base: 'initial' },
  })
  await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/journal/9'))
})

it('a server {ok:false} reply is shown inside the account form, which stays open', async () => {
  mockApi({ 'POST /api/journal/accounts': () => ({ ok: false, error: 'Account size must be positive' }) })
  mount('/journal?new=1')
  await screen.findByRole('dialog')
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
  expect(await screen.findByText('Account size must be positive')).toBeInTheDocument()
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})

it('the trade form posts the same body as the old tradeBody() and closes after saving', async () => {
  mockApi()
  mount('/journal')
  fireEvent.click(await screen.findByRole('button', { name: '＋ Add trade' }))
  const dlg = await screen.findByRole('dialog', { name: 'Add trade' })
  await waitFor(() => expect(within(dlg).getByLabelText('Phase')).toHaveValue('1'))
  typeInto('Opened', '2026-11-01T10:30')
  typeInto('Closed', '2026-11-01T11:30')
  typeInto('Lots', '0.1'); typeInto('Entry', '2000'); typeInto('Stop', '1990'); typeInto('Target', '2020'); typeInto('Exit', '2010')
  typeInto(/Commission/, '0.6'); typeInto('Setup', 'Breakout')
  fireEvent.click(within(dlg).getByRole('button', { name: 'SELL' }))
  fireEvent.click(within(dlg).getByRole('button', { name: 'Yes' }))
  fireEvent.click(within(dlg).getByRole('button', { name: '3 stars' }))
  fireEvent.click(within(dlg).getByRole('button', { name: 'Calm' }))
  typeInto(/Mistakes/, 'none'); typeInto('Notes', 'ok')
  fireEvent.click(within(dlg).getByRole('button', { name: 'Add to journal' }))
  await waitFor(() => expect(posted('POST', '/api/journal/trades')).toBeTruthy())
  expect(posted('POST', '/api/journal/trades')!.body).toEqual({
    account_id: 5, phase_id: 1, symbol: 'XAUUSD', side: 'SELL',
    opened_at: Math.round(Date.parse('2026-11-01T10:30') / 1000), closed_at: Math.round(Date.parse('2026-11-01T11:30') / 1000),
    lots: 0.1, entry: 2000, stop: 1990, target: 2020, exit: 2010, pnl: null, commission: 0.6, setup: 'Breakout',
    followed_plan: 1, rating: 3, emotion: 'Calm', mistakes: 'none', notes: 'ok', image_data: null,
  })
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

it('Escape closes the account form and focus stays inside the dialog on Tab', async () => {
  mockApi()
  mount('/journal?new=1')
  const dlg = await screen.findByRole('dialog')
  const close = within(dlg).getByRole('button', { name: /^Close/ })
  fireEvent.keyDown(close, { key: 'Tab', shiftKey: true })
  expect(dlg.contains(document.activeElement)).toBe(true)
  fireEvent.keyDown(document.body, { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

it('Escape closes the trade form without saving', async () => {
  mockApi()
  mount('/journal')
  fireEvent.click(await screen.findByRole('button', { name: '＋ Add trade' }))
  const dlg = await screen.findByRole('dialog', { name: 'Add trade' })
  fireEvent.keyDown(dlg, { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(calls.some((c) => c.method === 'POST')).toBe(false)
})

it('a screenshot is read to a data URL and sent as image_data; over 6 MB is refused', async () => {
  const small = new File([new Uint8Array([137, 80, 78, 71])], 's.png', { type: 'image/png' })
  expect(await readImage(small)).toMatch(/^data:image\/png;base64,/)
  const big = new File([new Uint8Array(6 * 1024 * 1024 + 1)], 'b.png', { type: 'image/png' })
  await expect(readImage(big)).rejects.toThrow('Screenshot must be under 6 MB.')

  mockApi()
  mount('/journal')
  fireEvent.click(await screen.findByRole('button', { name: '＋ Add trade' }))
  const dlg = await screen.findByRole('dialog')
  typeInto('Opened', '2026-11-01T10:30')
  fireEvent.change(within(dlg).getByLabelText('Screenshot'), { target: { files: [small] } })
  await within(dlg).findByAltText('Trade screenshot')
  fireEvent.click(within(dlg).getByRole('button', { name: 'Add to journal' }))
  await waitFor(() => expect(posted('POST', '/api/journal/trades')).toBeTruthy())
  expect((posted('POST', '/api/journal/trades')!.body as { image_data: string }).image_data).toMatch(/^data:image\/png;base64,/)
})

it('a missing open time and a server {ok:false} are shown in the trade form', async () => {
  mockApi({ 'POST /api/journal/trades': () => ({ ok: false, error: 'Stop is on the wrong side' }) })
  mount('/journal')
  fireEvent.click(await screen.findByRole('button', { name: '＋ Add trade' }))
  const dlg = await screen.findByRole('dialog')
  typeInto('Opened', '')
  fireEvent.click(within(dlg).getByRole('button', { name: 'Add to journal' }))
  expect(await within(dlg).findByText('Set the open time.')).toBeInTheDocument()
  expect(posted('POST', '/api/journal/trades')).toBeUndefined()
  typeInto('Opened', '2026-11-01T10:30')
  fireEvent.click(within(dlg).getByRole('button', { name: 'Add to journal' }))
  expect(await within(dlg).findByText('Stop is on the wrong side')).toBeInTheDocument()
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})

it('?call=1 (dashboard "Add to my journal") opens the trade form pre-filled like addCall()', async () => {
  mockApi()
  mount('/journal?call=1')
  const dlg = await screen.findByRole('dialog', { name: 'Add AuEdge call to journal' })
  expect(screen.getByTestId('where')).toHaveTextContent(/^\/journal$/)
  expect(within(dlg).getByRole('button', { name: 'SELL' })).toHaveAttribute('aria-pressed', 'true')
  expect(within(dlg).getByLabelText('Entry')).toHaveValue(2000) // mid of 1999.5 / 2000.5
  expect(within(dlg).getByLabelText('Stop')).toHaveValue(2010)
  expect(within(dlg).getByLabelText('Target')).toHaveValue(1970)
  expect(within(dlg).getByLabelText('Setup')).toHaveValue('AuEdge NOW call')
  expect(within(dlg).getByText(/From AuEdge: SELL NOW · confidence 72%/)).toBeInTheDocument()
  fireEvent.click(within(dlg).getByRole('button', { name: 'Add to journal' }))
  await waitFor(() => expect(posted('POST', '/api/journal/trades')).toBeTruthy())
  const b = posted('POST', '/api/journal/trades')!.body as Record<string, unknown>
  expect(b).toMatchObject({ side: 'SELL', entry: 2000, stop: 2010, target: 1970, setup: 'AuEdge NOW call', source: 'auedge', account_id: 5, phase_id: 1 })
  expect(b.auedge).toEqual({ action: 'SELL NOW', confidence: 72, t: Math.round(Date.parse('2026-11-01T10:00:00Z') / 1000), be_at: 1990 })
})

it('CSV export has the old header row and quotes cells', async () => {
  expect(CSV_COLS.join(',')).toBe('day,opened_at,closed_at,account,phase,symbol,side,lots,entry,stop,target,exit,pnl,commission,net,planned_rr,r,setup,emotion,followed_plan,rating,source,mistakes,notes')
  const text = csvText([T1 as never])
  const [head, row] = text.split('\n')
  expect(head).toBe(CSV_COLS.join(','))
  expect(row).toContain(new Date(T1.opened_at * 1000).toISOString())
  expect(row.endsWith('"Clean ""one"""')).toBe(true)

  mockApi()
  const urls: Blob[] = []
  URL.createObjectURL = vi.fn((b: Blob) => { urls.push(b); return 'blob:x' }) as never
  URL.revokeObjectURL = vi.fn() as never
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  mount('/journal')
  await screen.findByText('Breakout', { selector: 'span' })
  fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }))
  expect(click).toHaveBeenCalled()
  expect(urls).toHaveLength(1)
  expect((await urls[0].text()).split('\n')[0]).toBe(CSV_COLS.join(','))
})

it('All records filters by result and search text', async () => {
  mockApi()
  mount('/journal')
  await screen.findByText('Breakout', { selector: 'span' })
  expect(screen.getByText('London sweep', { selector: 'span' })).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Result'), { target: { value: 'loss' } })
  expect(screen.queryByText('Breakout', { selector: 'span' })).not.toBeInTheDocument()
  expect(screen.getByText('London sweep', { selector: 'span' })).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Result'), { target: { value: '' } })
  fireEvent.change(screen.getByLabelText('Search notes'), { target: { value: 'revenge' } })
  expect(screen.queryByText('Breakout', { selector: 'span' })).not.toBeInTheDocument()
  expect(screen.getByText('London sweep', { selector: 'span' })).toBeInTheDocument()
})

it('a trade row opens its form from the keyboard and Delete calls DELETE after confirm', async () => {
  mockApi()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  mount('/journal/5')
  const row = (await screen.findByText('Breakout', { selector: 'span' })).closest('tr')!
  expect(row).toHaveAttribute('tabindex', '0')
  fireEvent.keyDown(row, { key: 'Enter' })
  const dlg = await screen.findByRole('dialog', { name: 'Trade' })
  expect(within(dlg).getByLabelText('Entry')).toHaveValue(2000)
  fireEvent.click(within(dlg).getByRole('button', { name: 'Delete trade' }))
  await waitFor(() => expect(posted('DELETE', '/api/journal/trades/11')).toBeTruthy())
})

it('editing a trade PUTs to its id', async () => {
  mockApi()
  mount('/journal/5')
  fireEvent.keyDown((await screen.findByText('Breakout', { selector: 'span' })).closest('tr')!, { key: ' ' })
  const dlg = await screen.findByRole('dialog')
  typeInto('Exit', '2015')
  fireEvent.click(within(dlg).getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(posted('PUT', '/api/journal/trades/11')).toBeTruthy())
  expect(posted('PUT', '/api/journal/trades/11')!.body).toMatchObject({ exit: 2015, account_id: 5, phase_id: 1, entry: 2000 })
})

it('Mark passed / failed / Undo call the right endpoint with the old bodies', async () => {
  mockApi()
  const prompt = vi.spyOn(window, 'prompt').mockReturnValueOnce('firm ok').mockReturnValueOnce('10000')
  mount('/journal/5')
  fireEvent.click(await screen.findByRole('button', { name: /Mark Phase 1 passed → start Phase 2/ }))
  await waitFor(() => expect(posted('POST', '/api/journal/accounts/5/advance')).toBeTruthy())
  expect(posted('POST', '/api/journal/accounts/5/advance')!.body).toEqual({ result: 'passed', note: 'firm ok', next_balance: 10000 })
  expect(prompt).toHaveBeenCalledTimes(2)

  prompt.mockReset().mockReturnValueOnce('blew it')
  fireEvent.click(await screen.findByRole('button', { name: 'Mark phase failed' }))
  await waitFor(() => expect(calls.filter((c) => c.url.endsWith('/advance'))).toHaveLength(2))
  expect(calls.filter((c) => c.url.endsWith('/advance'))[1].body).toEqual({ result: 'failed', note: 'blew it', next_balance: null })
})

it('Undo shows for the phase before the active one and POSTs reopen', async () => {
  const two = accOf([phase(1, 0, { result: 'passed' }), phase(2, 1)])
  mockApi({}, { ...two, trades: [] })
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  mount('/journal/5')
  fireEvent.click(await screen.findByRole('button', { name: /Phase 1$/ }))
  fireEvent.click(await screen.findByRole('button', { name: 'Undo passed mark' }))
  await waitFor(() => expect(posted('POST', '/api/journal/accounts/5/reopen')).toBeTruthy())
})

it('a refused phase mark shows the server text', async () => {
  mockApi({ 'POST /api/journal/accounts/5/advance': () => ({ ok: false, error: 'Phase already closed' }) })
  vi.spyOn(window, 'prompt').mockReturnValue('x')
  mount('/journal/5')
  fireEvent.click(await screen.findByRole('button', { name: 'Mark phase failed' }))
  expect(await screen.findByText('Phase already closed')).toBeInTheDocument()
})

it('Archive PUTs the old body', async () => {
  mockApi()
  mount('/journal/5')
  fireEvent.click(await screen.findByRole('button', { name: 'Archive' }))
  await waitFor(() => expect(posted('PUT', '/api/journal/accounts/5')).toBeTruthy())
  expect(posted('PUT', '/api/journal/accounts/5')!.body).toEqual({ name: 'FTMO 10k', firm: 'FTMO', notes: '', archived: true })
})

const ACC5two = accOf([phase(1, 0, { result: 'passed' }), phase(2, 1)])
const ACC6 = (o: Record<string, unknown> = {}) => accOf([phase(20, 0, { account_id: 6, ...o })], { id: 6, name: 'Other 5k' })
const T3 = trade(13, { account_id: 5, net: -20, r: -0.2, setup: 'Range fade', day: '2026-09-15', notes: '' })

it('editing: an account with no open phase falls back to a real phase id, and switching back restores the trade phase', async () => {
  mockApi({ 'GET /api/journal/accounts': () => ({ accounts: [ACC5two, ACC6({ result: 'passed' })], now: NOW }) })
  mount('/journal')
  fireEvent.keyDown((await screen.findByText('Breakout', { selector: 'span' })).closest('tr')!, { key: 'Enter' })
  const dlg = await screen.findByRole('dialog', { name: 'Trade' })
  const phaseSel = within(dlg).getByLabelText('Phase')
  await waitFor(() => expect(phaseSel).toHaveValue('1'))
  fireEvent.change(within(dlg).getByLabelText('Account'), { target: { value: '6' } })
  expect(phaseSel).toHaveValue('20')
  fireEvent.change(within(dlg).getByLabelText('Account'), { target: { value: '5' } })
  expect(phaseSel).toHaveValue('1') // the trade's own phase, not the open Phase 2
  fireEvent.change(within(dlg).getByLabelText('Account'), { target: { value: '6' } })
  fireEvent.click(within(dlg).getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(posted('PUT', '/api/journal/trades/11')).toBeTruthy())
  expect(posted('PUT', '/api/journal/trades/11')!.body).toMatchObject({ account_id: 6, phase_id: 20 })
})

it('a trade moved to another account takes you to that account after saving', async () => {
  mockApi({ 'GET /api/journal/accounts': () => ({ accounts: [ACC, ACC6()], now: NOW }) })
  mount('/journal/5')
  fireEvent.keyDown((await screen.findByText('Breakout', { selector: 'span' })).closest('tr')!, { key: 'Enter' })
  const dlg = await screen.findByRole('dialog', { name: 'Trade' })
  await waitFor(() => expect(within(dlg).getByLabelText('Account')).toHaveValue('5'))
  fireEvent.change(within(dlg).getByLabelText('Account'), { target: { value: '6' } })
  fireEvent.click(within(dlg).getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/journal/6'))
})

it('the risk text has a thousands separator', async () => {
  mockApi()
  mount('/journal')
  fireEvent.click(await screen.findByRole('button', { name: '＋ Add trade' }))
  await screen.findByRole('dialog')
  typeInto('Lots', '1'); typeInto('Entry', '2000'); typeInto('Stop', '1900')
  expect(await screen.findByText(/Risk if the stop is hit:/)).toHaveTextContent('Risk if the stop is hit: $10,000 (100.00% of the account)')
})

it('All records is a headed table with the old columns, AuEdge chip under Side, and a back link', async () => {
  mockApi({ 'GET /api/journal/trades': () => ({ trades: [trade(11, { source: 'auedge' }), T2] }) })
  mount('/journal')
  await screen.findByText('Breakout', { selector: 'span' })
  expect(screen.getByRole('link', { name: '← All accounts' })).toHaveAttribute('href', '/dashboard')
  const table = screen.getByRole('table')
  expect(within(table).getAllByRole('columnheader').map((h) => h.textContent))
    .toEqual(['Opened', 'Account', 'Side', 'Lots', 'Entry → exit', 'Setup', 'R:R plan', 'R', 'Net'])
  const cells = within(within(table).getByText('Breakout', { selector: 'span' }).closest('tr')!).getAllByRole('cell')
  expect(cells).toHaveLength(9)
  expect(within(cells[2]).getByText('BUY')).toBeInTheDocument()
  expect(within(cells[2]).getByText('AuEdge')).toBeInTheDocument()
  expect(within(cells[1]).getByText('FTMO 10k')).toBeInTheDocument()
  expect(within(cells[1]).getByText('Phase 1')).toBeInTheDocument()
})

it('under 640 px each trade is a two-line card with Net, openable by keyboard', async () => {
  mockApi({ 'GET /api/journal/trades': () => ({ trades: [trade(11, { source: 'auedge' }), T2] }) })
  mount('/journal')
  await screen.findAllByTestId('trade-card')
  const cards = screen.getAllByTestId('trade-card')
  expect(cards).toHaveLength(2)
  expect(cards[0]).toHaveTextContent('BUY')
  expect(cards[0]).toHaveTextContent('0.1 lot')
  expect(cards[0]).toHaveTextContent('+$100')
  expect(cards[0]).toHaveTextContent('2,000.00 → 2,010.00 · Breakout · R:R 1:2 · +1.00R')
  expect(cards[0]).toHaveTextContent('AuEdge')
  expect(cards[0]).toHaveTextContent('FTMO 10k') // All records shows the account
  expect(cards[1]).toHaveTextContent('−$50')
  expect(cards[1]).toHaveTextContent('−0.50R')
  // the card layout is the one shown under 640 px; the table is its sm-and-up sibling
  expect(cards[0].parentElement!.className).toContain('sm:hidden')
  expect(screen.getByRole('table').closest('div.hidden')!.className).toContain('sm:block')
  fireEvent.keyDown(cards[1], { key: 'Enter' })
  expect(await screen.findByRole('dialog', { name: 'Trade' })).toBeInTheDocument()
})

it('the account Journal tab is a headed table with Plan and Mood columns', async () => {
  mockApi()
  mount('/journal/5')
  await screen.findByText('Breakout', { selector: 'span' })
  expect(within(screen.getByRole('table')).getAllByRole('columnheader').map((h) => h.textContent))
    .toEqual(['Opened', 'Side', 'Lots', 'Entry → exit', 'Setup', 'Plan', 'Mood', 'R:R plan', 'R', 'Net'])
})

it('the records calendar keeps its month when a filter changes', async () => {
  mockApi({ 'GET /api/journal/trades': () => ({ trades: [T1, T2, T3] }) })
  mount('/journal')
  await screen.findAllByText('Range fade', { selector: 'span' })
  fireEvent.click(screen.getByRole('button', { name: 'Calendar' }))
  expect(await screen.findByText(/October 2026/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Previous month' }))
  expect(screen.getByText(/September 2026/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Result'), { target: { value: 'loss' } })
  expect(screen.getByText(/September 2026/)).toBeInTheDocument()
})

it('the account page shows figures, meters, tabs and the calendar day trades', async () => {
  mockApi()
  mount('/journal/5')
  await screen.findByText('Phase 1 · started', { exact: false })
  expect(screen.getByText('Profit this phase').nextElementSibling).toHaveTextContent('+$50')
  expect(screen.getByText("Today's loss room")).toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: 'Calendar' }))
  const day = (await screen.findAllByTestId('jcal-day')).find((b) => b.getAttribute('data-day') === '2026-10-30')!
  fireEvent.click(day)
  expect(await screen.findByText('Breakout', { selector: 'span' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: 'Risk : Reward' }))
  expect(await screen.findByText(/Record entry, stop, target and lots/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: 'Consistency' }))
  expect(await screen.findByText('Shown once this phase is in profit.')).toBeInTheDocument()
})
