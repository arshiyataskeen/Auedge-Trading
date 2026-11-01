import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import SeparationCard from './SeparationCard'

const row = (agent: string, verdict: string, o: Record<string, unknown> = {}) => ({
  agent, n: 300, mean: 0.12, hit_rate: 54.3, distance: 0.0412, lo: 0.0301, hi: 0.0622, verdict, drift: null, source: 'dataset.db steps', ...o,
})
const DATA = [
  row('smc', 'useful', { drift: { recent_n: 40, prior_n: 200, recent_distance: 0.09, prior_distance: 0.02, recent_mean: 0.2, prior_mean: 0.1, diff: 0.07, lo: 0.01, hi: 0.1, flag: true } }),
  row('elliott', 'none'),
  row('skeptic', 'harmful', { mean: -0.2 }),
  row('sentiment', 'too_few', { n: 12, distance: 0.04, lo: null, hi: null }),
]
afterEach(() => vi.unstubAllGlobals())
function mount() {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(DATA), { status: 200 })))
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SeparationCard /></QueryClientProvider>)
}

it('explains itself in plain words and shows a verdict chip per agent', async () => {
  mount()
  expect(await screen.findByText(/Signal separation \(does gold behave differently after this agent's calls\?\)/)).toBeInTheDocument()
  const cards = await screen.findAllByTestId('sep-card')
  expect(cards).toHaveLength(4)
  expect(within(cards[0]).getByText('Useful')).toBeInTheDocument()
  expect(within(cards[1]).getByText('No clear signal')).toBeInTheDocument()
  expect(within(cards[2]).getByText('Harmful')).toBeInTheDocument()
  expect(within(cards[3]).getByText('Too few calls')).toBeInTheDocument()
})

it('shows n, distance with its interval, and the drift note only when flagged', async () => {
  mount()
  const cards = await screen.findAllByTestId('sep-card')
  expect(within(cards[0]).getByText(/0\.041 \(0\.030 to 0\.062\)/)).toBeInTheDocument()
  expect(within(cards[0]).getByText(/Behaving differently lately/)).toBeInTheDocument()
  expect(within(cards[1]).queryByText(/Behaving differently lately/)).not.toBeInTheDocument()
})

it('renders both a headed table and compact cards (CSS picks one by width)', async () => {
  mount()
  await screen.findAllByTestId('sep-card')
  expect(screen.getByRole('table')).toBeInTheDocument()
  expect(screen.getAllByRole('columnheader').length).toBeGreaterThanOrEqual(6)
})
