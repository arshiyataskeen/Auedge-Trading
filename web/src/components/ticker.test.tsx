import { render, screen, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import NewsTicker from './NewsTicker'
import SessionsDial from './SessionsDial'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })
const mk = (events: unknown[]) => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ now: 0, blocking: null, events }), { status: 200 })))
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><NewsTicker /></QueryClientProvider>)
}
describe('NewsTicker', () => {
  const now = Date.now() / 1000
  it('shows upcoming High events with pill and countdown', async () => {
    mk([{ impact: 'High', t: now + 2 * 86400 + 3 * 3600 + 60, name: 'CPI' }, { impact: 'Low', t: now + 100, name: 'Minor' }])
    expect((await screen.findAllByText('CPI')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('HIGH IMPACT').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/in 2d 3h/).length).toBeGreaterThan(0)
    expect(screen.queryByText('Minor')).toBeNull()
  })
  it('is hidden when no events', async () => {
    mk([])
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByTestId('news-ticker')).toBeNull()
  })
})
describe('SessionsDial', () => {
  it('shows weekend closed on a Saturday', () => {
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date(Date.UTC(2026, 0, 17, 12, 0)))
    render(<SessionsDial />)
    expect(screen.getByTestId('dial-status')).toHaveTextContent('Weekend: market closed')
    expect(screen.getByTestId('chip-london')).toHaveTextContent('opens in')
  })
  it('shows London open midweek', () => {
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date(Date.UTC(2026, 0, 14, 10, 0)))
    render(<SessionsDial />)
    expect(screen.getByTestId('chip-london')).toHaveTextContent('closes in 7h 0m')
  })
})
