import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { getJSON } from './client'
import { useRunBacktest, useCreateTrade, useUpdateTrade, useBacktestStatus, useRunReview, useReviewVote, useRefreshAnalysis, qk } from './endpoints'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const spy = vi.spyOn(qc, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  return { qc, spy, wrapper }
}

it('200 {ok:false} is an error with the server text and does not invalidate', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ ok: false, error: 'x' })))
  const { spy, wrapper } = setup()
  const { result } = renderHook(() => useRunBacktest(), { wrapper })
  act(() => { result.current.mutate({} as never) })
  await waitFor(() => expect(result.current.isError).toBe(true))
  expect(result.current.error?.message).toBe('x')
  expect(spy).not.toHaveBeenCalled()
})

it('review mutation with ok:false does not invalidate either', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ ok: false, error: 'busy' })))
  const { spy, wrapper } = setup()
  const { result } = renderHook(() => useRunReview(), { wrapper })
  act(() => { result.current.mutate(false) })
  await waitFor(() => expect(result.current.error?.message).toBe('busy'))
  expect(spy).not.toHaveBeenCalled()
})

it('run backtest sends POST /api/backtest/run with JSON body, then invalidates', async () => {
  const f = vi.fn().mockResolvedValue(json({ ok: true, id: 'bt_1' }))
  vi.stubGlobal('fetch', f)
  const { spy, wrapper } = setup()
  const { result } = renderHook(() => useRunBacktest(), { wrapper })
  act(() => { result.current.mutate({ start: 'a', end: 'b' } as never) })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  const [url, init] = f.mock.calls[0]
  expect(url).toBe('/api/backtest/run')
  expect(init.method).toBe('POST')
  expect(init.body).toBe('{"start":"a","end":"b"}')
  expect(spy).toHaveBeenCalled()
})

it('journal trade save sends POST /api/journal/trades and PUT /api/journal/trades/:id', async () => {
  const f = vi.fn().mockImplementation(async () => json({ ok: true, id: 3 }))
  vi.stubGlobal('fetch', f)
  const { wrapper } = setup()
  const c = renderHook(() => useCreateTrade(), { wrapper })
  act(() => { c.result.current.mutate({ account_id: 2, opened_at: 5 }) })
  await waitFor(() => expect(c.result.current.isSuccess).toBe(true))
  expect(f.mock.calls[0][0]).toBe('/api/journal/trades')
  expect(f.mock.calls[0][1].method).toBe('POST')
  expect(f.mock.calls[0][1].body).toBe('{"account_id":2,"opened_at":5}')
  const u = renderHook(() => useUpdateTrade(), { wrapper })
  act(() => { u.result.current.mutate({ id: 7, body: { notes: 'n' } }) })
  await waitFor(() => expect(u.result.current.isSuccess).toBe(true))
  expect(f.mock.calls[1][0]).toBe('/api/journal/trades/7')
  expect(f.mock.calls[1][1].method).toBe('PUT')
})

it('useBacktestStatus(false) does not poll; (true) does', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  const f = vi.fn().mockImplementation(async () => json({ running: false }))
  vi.stubGlobal('fetch', f)
  const { wrapper } = setup()
  const off = renderHook(() => useBacktestStatus(false), { wrapper })
  await waitFor(() => expect(off.result.current.isSuccess).toBe(true))
  await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
  expect(f).toHaveBeenCalledTimes(1)
  off.unmount()
  f.mockClear()
  const { wrapper: w2 } = setup()
  const on = renderHook(() => useBacktestStatus(true), { wrapper: w2 })
  await waitFor(() => expect(on.result.current.isSuccess).toBe(true))
  await act(async () => { await vi.advanceTimersByTimeAsync(4000) })
  expect(f.mock.calls.length).toBeGreaterThanOrEqual(3)
})

it('non-2xx includes the server detail/error text; bad JSON becomes ApiError', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(json({ detail: 'nope' }, 422))
    .mockResolvedValueOnce(json({ error: 'bad' }, 500))
    .mockResolvedValueOnce(new Response('<html>', { status: 200 })))
  await expect(getJSON('/a')).rejects.toMatchObject({ status: 422, message: 'HTTP 422: nope' })
  await expect(getJSON('/a')).rejects.toMatchObject({ status: 500, message: 'HTTP 500: bad' })
  await expect(getJSON('/a')).rejects.toMatchObject({ name: 'ApiError', message: 'Invalid response from server' })
})

it('review mutations invalidate the review list but not the analysis (the page refreshes it explicitly)', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ ok: true })))
  const { spy, wrapper } = setup()
  const { result } = renderHook(() => useReviewVote(), { wrapper })
  act(() => { result.current.mutate({ agent: 'ict', on: false }) })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  const keys = spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey))
  expect(keys).toContain(JSON.stringify(qk.review))
  expect(keys).not.toContain(JSON.stringify(qk.analysis))
})

it('refresh=true wins over a plain analysis GET that lands after it', async () => {
  let releasePlain: (r: Response) => void = () => {}
  vi.stubGlobal('fetch', vi.fn((url: string) => url.includes('refresh=true')
    ? Promise.resolve(json({ v: 'fresh' }))
    : new Promise<Response>((res) => { releasePlain = res })))
  const { qc, wrapper } = setup()
  qc.setQueryData(qk.analysis, { v: 'old' })
  const plain = qc.fetchQuery({ queryKey: qk.analysis, queryFn: () => getJSON('/api/analysis'), staleTime: 0 }).catch(() => null)
  const { result } = renderHook(() => useRefreshAnalysis(), { wrapper })
  await act(async () => { await result.current.mutateAsync() })
  releasePlain(json({ v: 'stale' }))
  await plain
  expect(qc.getQueryData(qk.analysis)).toEqual({ v: 'fresh' })
})
