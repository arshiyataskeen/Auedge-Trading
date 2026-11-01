import { act, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { News, NewsEvent } from '../../api/types'
import NewsPage from './index'

const sec = (d: Date) => Math.floor(d.getTime() / 1000)
const NOW = new Date(2026, 5, 2, 8, 0, 0) // local 08:00
const at = (day: number, h: number, mi = 0) => sec(new Date(2026, 5, day, h, mi))
const ev = (p: Partial<NewsEvent> & { t: number; name: string }): NewsEvent => ({
  impact: 'High', forecast: '', previous: '', blocks: true, win_from: p.t - 1800, win_to: p.t + 1800, source: 'ForexFactory', ...p,
})
const past = ev({ t: at(2, 6), name: 'ADP Employment', impact: 'Medium', blocks: false, forecast: '100K', previous: '90K' })
const live = ev({ t: at(2, 8, 10), name: 'ISM Services PMI', forecast: '52.1', previous: '51.0' })
const later = ev({ t: at(3, 9), name: 'Nonfarm Payrolls', source: 'BLS' })
const body = (blocking: NewsEvent | null): News => ({ now: sec(NOW), blocking, events: [past, live, later] })

const fmtT = (s: number) => new Date(s * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
const fmtD = (s: number) => new Date(s * 1000).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' })

function mockApi(news: News) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(news), { status: 200 })))
}
async function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={qc}><NewsPage /></QueryClientProvider>)
  await act(async () => { await new Promise((r) => setTimeout(r, 30)) })
}

beforeEach(() => { vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] }); vi.setSystemTime(NOW) })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it('groups events by local day and shows time, chip, forecast/previous, no-trade tag', async () => {
  mockApi(body(null))
  await mount()
  const headers = document.querySelectorAll('[data-testid="news-day"]')
  expect(headers).toHaveLength(2)
  expect(headers[0].textContent).toBe(fmtD(past.t))
  expect(headers[1].textContent).toBe(fmtD(later.t))
  const rows = screen.getAllByTestId('news-row')
  expect(rows).toHaveLength(3)
  expect(within(rows[0]).getByText(fmtT(past.t))).toBeTruthy()
  expect(within(rows[0]).getByText('MEDIUM')).toBeTruthy()
  expect(within(rows[0]).getByText('forecast 100K · previous 90K')).toBeTruthy()
  expect(within(rows[0]).queryByText('no-trade window')).toBeNull()
  expect(within(rows[1]).getByText('HIGH')).toBeTruthy()
  expect(within(rows[1]).getByText('no-trade window')).toBeTruthy()
  expect(within(rows[2]).getByText('BLS')).toBeTruthy() // no forecast/previous -> source
  expect(within(rows[0]).getByText('2h 0m ago')).toBeTruthy()
  expect(within(rows[2]).getByText('in 1d 1h')).toBeTruthy()
})

it('shows the blocking banner while inside a no-trade window', async () => {
  vi.setSystemTime(new Date(2026, 5, 2, 8, 0)) // live window 07:40-08:40
  mockApi(body(live))
  await mount()
  const b = screen.getByTestId('news-banner')
  expect(b.textContent).toContain('No new trades now: ISM Services PMI')
  expect(b.textContent).toContain(`window until ${fmtT(live.win_to)}`)
})

it('shows the all-clear banner with the next blocking event countdown', async () => {
  vi.setSystemTime(new Date(2026, 5, 2, 6, 0)) // before live window (07:40)
  mockApi(body(null))
  await mount()
  expect(screen.getByTestId('news-banner').textContent).toBe('✓ No news window now: trading allowed · next: ISM Services PMI in 2h 10m')
  expect(screen.getByText(/Gold moves most on US data/)).toBeTruthy()
  expect(screen.getByText(/Sources: ForexFactory weekly calendar/)).toBeTruthy()
})

it('countdown and banner tick without a refetch', async () => {
  vi.setSystemTime(new Date(2026, 5, 2, 6, 0))
  mockApi(body(null))
  await mount()
  expect(screen.getByText('in 2h 10m', { selector: '[data-testid="news-row"] span' })).toBeTruthy()
  act(() => { vi.setSystemTime(new Date(2026, 5, 2, 6, 14, 30)); vi.advanceTimersByTime(30000) })
  expect(screen.getAllByText('in 1h 55m').length).toBeGreaterThan(0)
  act(() => { vi.setSystemTime(new Date(2026, 5, 2, 7, 49, 30)); vi.advanceTimersByTime(30000) })
  expect(screen.getByTestId('news-banner').textContent).toContain('No new trades now: ISM Services PMI')
})

it('shows an empty message when there are no events', async () => {
  mockApi({ now: sec(NOW), blocking: null, events: [] })
  await mount()
  expect(screen.getByText('No high or medium impact US events found.')).toBeTruthy()
})
