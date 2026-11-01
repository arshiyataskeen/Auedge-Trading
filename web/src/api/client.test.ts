import { afterEach, expect, it, vi } from 'vitest'
import { ApiError, getJSON, postJSON } from './client'

afterEach(() => vi.unstubAllGlobals())

it('getJSON throws ApiError with status', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('boom', { status: 500 })))
  await expect(getJSON('/api/x')).rejects.toMatchObject({ name: 'ApiError', status: 500 })
  await expect(getJSON('/api/x')).rejects.toBeInstanceOf(ApiError)
})

it('getJSON returns parsed body; postJSON sends JSON', async () => {
  const f = vi.fn().mockResolvedValue(new Response('{"ok":true}', { status: 200 }))
  vi.stubGlobal('fetch', f)
  expect(await postJSON('/api/y', { a: 1 })).toEqual({ ok: true })
  const init = f.mock.calls[0][1]
  expect(init.method).toBe('POST')
  expect(init.body).toBe('{"a":1}')
})

import { analysisInterval } from './endpoints'

it('analysis refetches when the next server step is due (+2 s), 60 s after a failure', () => {
  expect(analysisInterval({ state: { status: 'success', data: { next_in_s: 713 } as never } })).toBe(715_000)
  expect(analysisInterval({ state: { status: 'error' } })).toBe(60_000)
})
