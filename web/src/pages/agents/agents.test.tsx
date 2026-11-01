import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { CrowdCard } from './AgentCard'
import AgentsPage from './index'

const agent = (name: string, label: string, o: Record<string, unknown> = {}) => ({
  agent: name, status: 'OK', bias: 'WAIT', confidence: 40, headline: `${label} headline`, reasons: ['why one'], warnings: [], levels: [],
  timeframe: '1h', veto: false, metrics: {}, subtitle: 'Daily + 4H', bias_label: 'RANGE', rows: [['Daily stage', 'Trading range']],
  summary: `${label} summary text`, label, weight: 1, base_weight: 1, vote_off: false, perf_weight: 1, perf: null, ...o,
})
const AGENTS = [
  agent('wyckoff', 'Wyckoff', { bias: 'BUY', bias_label: 'BUY', perf: { hits: 60, n: 120, hit_rate: 55, shrunk: 54, mult: 1.1 }, weight: 0.8, base_weight: 0.75,
    levels: [{ kind: 'target', price: 4074.7, note: 'Wyckoff HTF target' }] }),
  agent('elliott', 'Elliott', { bias: 'SELL', bias_label: 'SELL', confidence: 70 }),
  agent('stophunt', 'Stop-hunt', { vote_off: true }),
  agent('sentiment', 'Market psychology', {
    metrics: { mood: 'GREED', greed: 2 }, bias: 'WAIT', rows: [['Mood', 'GREED'], ['Fear index', '61']], summary: 'The crowd is greedy.',
  }),
  agent('psychology', 'Discipline', { base_weight: undefined, weight: undefined, perf: undefined, subtitle: 'You' }),
]
const TRACK = {
  agents: {
    chief: { hits: 88, misses: 85, flat: 62, pending: 34, hit_rate: 51 }, wyckoff: { hits: 51, misses: 42, flat: 52, pending: 0, hit_rate: 55 },
    ict: { hits: 0, misses: 0, flat: 0, pending: 2, hit_rate: null },
  },
  trades: { won: 5, lost: 1, open: 0, expired: 2, win_rate: 83, avg_r: 0.45,
    recent: [{ ts: 1793000000, side: 'SELL', entry: 4100.5, stop: 4110, t1: 4080, status: 'won', result_r: 1.2 }] },
}
const ANALYSIS = {
  ai_enabled: false, generated_at: '2026-10-31T10:00:00Z', next_in_s: 600, perf_weights_on: false, adapter_problems: [], data_errors: [],
  data_check: { headline: 'Data fresh', veto: false, warnings: [] }, chief: { plan: { kind: 'none' } }, agents: AGENTS, track: TRACK,
}
const REVIEW = {
  votes: { off: ['stophunt'], auto_apply: false },
  log: [{ t: 1793032932, by: 'you', before: [], after: ['stophunt'], changes: [{ agent: 'stophunt', action: 'off' }], note: 'x', review: null }],
  last: { id: 'rv_1', made_at: 1793169218, apply: false, votes_before: ['stophunt'], votes_after: ['stophunt', 'ict'],
    changes: [{ agent: 'ict', action: 'off' }],
    candidates: [{ agent: 'ict', action: 'off', gain_6m: 94, halves_6m: [40, 54], gain_month: -12 }],
    confirm: null, summary: 'ICT looks weak.', rules: { noise_usd: 25, max_changes: 2, min_voters: 5 } },
  agents: [{ name: 'wyckoff', label: 'Wyckoff', weight: 0.75 }, { name: 'stophunt', label: 'Stop-hunt', weight: 1 }],
  next_due: 1793774018,
}
const TRV = {
  made_at: 1793515522, backtest: 'bt_1', n_live: 1, n_backtest: 1,
  live: [{ t: 1793332497, side: 'SELL', r: 1.24, usd: 394, won: true, why: 'target', for: ['smc'], against: ['elliott'], reasons: ['with_trend'], tags: {}, src: 'live' }],
  recent_backtest: [{ t: 1793000000, side: 'BUY', r: -1, usd: -100, won: false, why: 'stop', for: ['smc'], against: [], reasons: ['fast'], tags: {}, src: 'bt' }],
  agents: [{ agent: 'smc', helped: 32, hurt: 20, n: 52, acc: 0.615, verdict: 'strong' }],
  lessons: [], win_patterns: ['Traded with the trend in 30 of the last 30 wins'],
  conditions: [{ cond: 'trend', val: 'with', n: 67, win: 0.522, avg_r: 0.06, total_r: 3.95 }],
  reasons: {}, early_review_at: 0, labels: { smc: 'Smart money', elliott: 'Elliott' }, voting_off: [],
  reason_text: { fast: 'stopped within an hour' }, win_text: { with_trend: 'it went with the trend' },
}
const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200 })

let calls: { url: string; method: string; body: unknown }[]
function mockApi(over: Record<string, unknown> = {}) {
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined })
    const path = url.split('?')[0]
    if (path in over) return json(over[path])
    if (path === '/api/analysis') return json(ANALYSIS)
    if (path === '/api/review') return json(REVIEW)
    if (path === '/api/trade_review') return json(TRV)
    if (path === '/api/backtest/status') return json({ running: false })
    if (path.startsWith('/api/review/')) return json({ ok: true })
    return new Response('{}', { status: 404 })
  }))
}
const chip = (n: RegExp) => within(screen.getByRole('group', { name: 'Agent votes' })).getByRole('button', { name: n })
const posts = () => calls.filter((c) => c.method === 'POST')
function mount(route = '/agents') {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[route]}><AgentsPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}
beforeEach(() => { vi.clearAllMocks(); localStorage.clear() })
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('renders one card per agent with its label, weight text and hit rate', async () => {
  mockApi()
  mount()
  const cards = await screen.findAllByTestId('agent-card')
  expect(cards).toHaveLength(AGENTS.length)
  const w = cards[0]
  expect(within(w).getByText('Wyckoff')).toBeInTheDocument()
  expect(within(w).getByText('BUY')).toBeInTheDocument()
  expect(within(w).getByText(/Vote weight 0\.8 \(fixed\) · performance would give ×1\.10 \(right 55% of 120\)/)).toBeInTheDocument()
  expect(within(w).getByText(/55% right \(51\/93\)/)).toBeInTheDocument()
  expect(within(cards[2]).getByText(/Vote OFF/)).toBeInTheDocument()
  expect(within(cards[4]).queryByText(/Vote weight/)).not.toBeInTheDocument()
  expect(within(cards[4]).getByText(/track record: none yet/)).toBeInTheDocument()
})

it('keeps the crowd card off the Agents page (it belongs to the Trade plan); CrowdCard still renders it', async () => {
  mockApi()
  mount()
  await screen.findAllByTestId('agent-card')
  expect(screen.queryByText('Market psychology · how the crowd is behaving')).not.toBeInTheDocument()
  render(<CrowdCard a={AGENTS[3] as never} />)
  expect(screen.getByText('Market psychology · how the crowd is behaving')).toBeInTheDocument()
  expect(screen.getByText('Fear index')).toBeInTheDocument()
  expect(screen.getByText('No contrarian trade')).toBeInTheDocument()
})

it('orders the Agents tab: review board, trade reviewer, agent cards', async () => {
  mockApi()
  mount()
  const board = await screen.findByRole('region', { name: 'Review board' })
  const trv = await screen.findByRole('region', { name: 'Trade reviewer' })
  const card = (await screen.findAllByTestId('agent-card'))[0]
  expect(board.compareDocumentPosition(trv) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(trv.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

it('the subtitle shows data check, Claude summary, adapter problems and the OK agent count', async () => {
  mockApi({ '/api/analysis': { ...ANALYSIS, ai_enabled: true, adapter_problems: ['yahoo down', 'cot late'] } })
  mount()
  const sub = await screen.findByText(/data:/)
  expect(sub).toHaveTextContent('data: Data fresh · Claude summary on · adapter problems: yahoo down; cot late · agents OK: 5/5 · click any agent for details')
})

it('a vote is followed by GET /api/analysis?refresh=true; a run or auto toggle is not', async () => {
  mockApi()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  mount()
  await screen.findByRole('group', { name: 'Agent votes' })
  fireEvent.click(chip(/Wyckoff/))
  await waitFor(() => expect(calls.some((c) => c.url === '/api/analysis?refresh=true' && c.method === 'GET')).toBe(true))
  const n = calls.filter((c) => c.url === '/api/analysis?refresh=true').length
  fireEvent.click(screen.getByRole('button', { name: /Run review now/ }))
  await waitFor(() => expect(posts().some((p) => p.url === '/api/review/run')).toBe(true))
  fireEvent.click(screen.getByLabelText('Apply changes automatically'))
  await waitFor(() => expect(posts().some((p) => p.url === '/api/review/auto')).toBe(true))
  expect(calls.filter((c) => c.url === '/api/analysis?refresh=true')).toHaveLength(n)
})

it('a refused vote does not refresh the analysis', async () => {
  mockApi({ '/api/review/vote': { ok: false, error: 'nope' } })
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  mount()
  await screen.findByRole('group', { name: 'Agent votes' })
  fireEvent.click(chip(/Wyckoff/))
  await screen.findByRole('alert')
  expect(calls.some((c) => c.url === '/api/analysis?refresh=true')).toBe(false)
})

it('opens an agent card with Enter and shows its rows and levels; Escape closes', async () => {
  mockApi()
  mount()
  const cards = await screen.findAllByTestId('agent-card')
  fireEvent.keyDown(cards[0], { key: 'Enter' })
  const dlg = await screen.findByRole('dialog')
  expect(within(dlg).getByText('Trading range')).toBeInTheDocument()
  expect(within(dlg).getByText('4,074.70')).toBeInTheDocument()
  fireEvent.keyDown(document, { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

it('Review board vote toggle confirms, then posts to /api/review/vote', async () => {
  mockApi()
  const ask = vi.spyOn(window, 'confirm').mockReturnValue(true)
  mount()
  await screen.findByRole('group', { name: 'Agent votes' })
  fireEvent.click(chip(/Wyckoff/))
  expect(ask).toHaveBeenCalledWith('Switch OFF the Wyckoff vote? It is logged and can be undone.')
  await waitFor(() => expect(posts()).toHaveLength(1))
  expect(posts()[0]).toMatchObject({ url: '/api/review/vote', body: { agent: 'wyckoff', on: false } })
})

it('declining the vote confirmation posts nothing; switching a vote back on says so', async () => {
  mockApi()
  const ask = vi.spyOn(window, 'confirm').mockReturnValue(false)
  mount()
  await screen.findByRole('group', { name: 'Agent votes' })
  fireEvent.click(chip(/Wyckoff/))
  expect(posts()).toHaveLength(0)
  ask.mockReturnValue(true)
  fireEvent.click(chip(/Stop-hunt/))
  expect(ask).toHaveBeenLastCalledWith('Switch ON the Stop-hunt vote? It is logged and can be undone.')
  await waitFor(() => expect(posts()[0]).toMatchObject({ url: '/api/review/vote', body: { agent: 'stophunt', on: true } }))
})

it('shows the server error when a vote is refused', async () => {
  mockApi({ '/api/review/vote': { ok: false, error: 'at least 5 agents must keep voting' } })
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  mount()
  await screen.findByRole('group', { name: 'Agent votes' })
  fireEvent.click(chip(/Wyckoff/))
  expect(await screen.findByRole('alert')).toHaveTextContent('at least 5 agents must keep voting')
})

it('undo asks first; apply and run post; auto toggles', async () => {
  mockApi()
  const ask = vi.spyOn(window, 'confirm').mockReturnValue(false)
  mount()
  const undo = await screen.findByRole('button', { name: 'Undo last change' })
  fireEvent.click(undo)
  expect(ask).toHaveBeenCalledWith('Undo the last vote change?')
  expect(posts()).toHaveLength(0)
  ask.mockReturnValue(true)
  fireEvent.click(undo)
  await waitFor(() => expect(posts().map((p) => p.url)).toEqual(['/api/review/undo']))
  fireEvent.click(screen.getByRole('button', { name: 'Apply these changes' }))
  await waitFor(() => expect(posts()[1]).toMatchObject({ url: '/api/review/apply', body: { run_id: 'rv_1' } }))
  fireEvent.click(screen.getByRole('button', { name: /Run review now/ }))
  await waitFor(() => expect(posts()[2]).toMatchObject({ url: '/api/review/run', body: { dry_run: false } }))
  fireEvent.click(screen.getByLabelText('Apply changes automatically'))
  await waitFor(() => expect(posts()[3]).toMatchObject({ url: '/api/review/auto', body: { on: true } }))
})

it('hides Apply when the last review is not pending, and shows progress while a review runs', async () => {
  mockApi({
    '/api/review': { ...REVIEW, last: { ...REVIEW.last, apply: true } },
    '/api/backtest/status': { running: true, id: 'rv_2', progress: { done: 1, total: 4, phase: 'Replaying' } },
  })
  mount()
  expect(await screen.findByText(/Review running · Replaying · 25%/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Apply these changes' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Run review now/ })).toBeDisabled()
})

it('Trade reviewer shows patterns, scorecard, conditions and trade reasons', async () => {
  mockApi()
  mount()
  expect(await screen.findByText('Trade reviewer · studies every win and every loss')).toBeInTheDocument()
  expect(screen.getByText('Traded with the trend in 30 of the last 30 wins')).toBeInTheDocument()
  expect(screen.getByText('No repeated loss pattern yet.')).toBeInTheDocument()
  expect(screen.getByText('strong')).toBeInTheDocument()
  expect(screen.getByText('62%')).toBeInTheDocument()
  expect(screen.getByText('WON +1.24R')).toBeInTheDocument()
  expect(screen.getByText(/Why it worked: it went with the trend/)).toBeInTheDocument()
})

it('Track record tab shows weights and the scored trades', async () => {
  mockApi()
  mount()
  fireEvent.click(await screen.findByRole('tab', { name: 'Track record' }))
  expect(await screen.findByText('Agent vote weights · performance weights OFF (shown only)')).toBeInTheDocument()
  expect(screen.getByText('83%')).toBeInTheDocument()
  expect(screen.getByText('+0.45R')).toBeInTheDocument()
  expect(screen.getByText(/0 open · 2 expired after 24h/)).toBeInTheDocument()
  expect(screen.getByText('Chief direction')).toBeInTheDocument()
  expect(screen.getByText('88 right · 85 wrong · 34 waiting')).toBeInTheDocument()
})

it('Track record says so when the track record is unavailable', async () => {
  mockApi({ '/api/analysis': { ...ANALYSIS, track: null } })
  mount('/agents?tab=track')
  expect(await screen.findByText('Track record unavailable.')).toBeInTheDocument()
})
