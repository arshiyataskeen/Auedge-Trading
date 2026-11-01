import { useState } from 'react'
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Sidebar from './Sidebar'
import Tabs from './Tabs'
import ThemeToggle from './ThemeToggle'
import TopBar from './TopBar'
import { useLivePrice } from '../api/live'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); delete document.documentElement.dataset.theme })

describe('Sidebar', () => {
  it('renders the 7 items in order and marks the current route', () => {
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={['/journal/3']}><Sidebar /></MemoryRouter></QueryClientProvider>)
    const links = screen.getAllByRole('link').filter((l) => l.getAttribute('title') !== 'Old screen')
    expect(links.map((l) => l.textContent)).toEqual(['Dashboard', 'Trade', 'Backtest', 'Journal', 'Demo', 'News', 'Agents'])
    const cur = links.filter((l) => l.getAttribute('aria-current') === 'page')
    expect(cur).toHaveLength(1)
    expect(cur[0].textContent).toBe('Journal')
  })
})

describe('Sidebar news badge', () => {
  const mk = (events: unknown[]) => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ now: 0, blocking: null, events }), { status: 200 })))
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><Sidebar /></MemoryRouter></QueryClientProvider>)
  }
  const now = Date.now() / 1000
  it('counts High events due within 24 h only', async () => {
    mk([{ impact: 'High', t: now + 3600 }, { impact: 'High', t: now + 7200 }, { impact: 'High', t: now + 90000 },
      { impact: 'Medium', t: now + 3600 }, { impact: 'High', t: now - 60 }])
    expect(await screen.findByTestId('news-badge')).toHaveTextContent('2')
  })
  it('is hidden when there are none', async () => {
    mk([{ impact: 'Medium', t: now + 3600 }])
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByTestId('news-badge')).toBeNull()
  })
  it('has an unobtrusive link to the old screen', () => {
    mk([])
    expect(screen.getByTitle('Old screen')).toHaveAttribute('href', '/old')
  })
})

describe('Tabs', () => {
  it('tabs show exactly one panel', () => {
    const items = [{ key: 'a', label: 'A' }, { key: 'b', label: 'B' }, { key: 'c', label: 'C' }]
    function Host() {
      const [v, setV] = useState('a')
      return <Tabs items={items} value={v} onChange={setV}>{items.map((i) => <div key={i.key} data-panel={i.key}>{i.label} body</div>)}</Tabs>
    }
    render(<Host />)
    expect(screen.getByRole('tablist')).toBeInTheDocument()
    for (const k of ['B', 'C', 'A']) {
      fireEvent.click(screen.getByRole('tab', { name: k }))
      expect(screen.getAllByRole('tabpanel')).toHaveLength(1)
      expect(screen.getByRole('tabpanel')).toHaveTextContent(`${k} body`)
    }
  })
  it('uses roving tabindex and arrow keys', () => {
    const items = [{ key: 'a', label: 'A' }, { key: 'b', label: 'B' }, { key: 'c', label: 'C' }]
    const onChange = vi.fn()
    render(<Tabs items={items} value="a" onChange={onChange} />)
    expect(screen.getByRole('tab', { name: 'A' })).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('tab', { name: 'B' })).toHaveAttribute('tabindex', '-1')
    fireEvent.keyDown(screen.getByRole('tab', { name: 'A' }), { key: 'ArrowRight' })
    expect(onChange).toHaveBeenLastCalledWith('b')
    fireEvent.keyDown(screen.getByRole('tab', { name: 'A' }), { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenLastCalledWith('c')
  })
  it('Home and End jump to the first and last tab', () => {
    const items = [{ key: 'a', label: 'A' }, { key: 'b', label: 'B' }, { key: 'c', label: 'C' }]
    const onChange = vi.fn()
    render(<Tabs items={items} value="b" onChange={onChange} />)
    fireEvent.keyDown(screen.getByRole('tab', { name: 'B' }), { key: 'End' })
    expect(onChange).toHaveBeenLastCalledWith('c')
    fireEvent.keyDown(screen.getByRole('tab', { name: 'B' }), { key: 'Home' })
    expect(onChange).toHaveBeenLastCalledWith('a')
  })
  it('namespaces ids per instance and only the active tab has aria-controls', () => {
    const items = [{ key: 'a', label: 'A' }, { key: 'b', label: 'B' }]
    render(<><Tabs items={items} value="a" onChange={() => {}}><i>1a</i><i>1b</i></Tabs><Tabs items={items} value="a" onChange={() => {}}><i>2a</i><i>2b</i></Tabs></>)
    const ids = Array.from(document.querySelectorAll('[id]')).map((e) => e.id)
    expect(new Set(ids).size).toBe(ids.length)
    const tabs = screen.getAllByRole('tab')
    const panels = screen.getAllByRole('tabpanel')
    expect(panels).toHaveLength(2)
    const active = tabs.filter((t) => t.getAttribute('aria-selected') === 'true')
    active.forEach((t, i) => {
      expect(t.getAttribute('aria-controls')).toBe(panels[i].id)
      expect(panels[i].getAttribute('aria-labelledby')).toBe(t.id)
    })
    tabs.filter((t) => t.getAttribute('aria-selected') !== 'true').forEach((t) => expect(t).not.toHaveAttribute('aria-controls'))
  })
})

describe('ThemeToggle', () => {
  it('sets data-theme and persists it', () => {
    render(<ThemeToggle />)
    fireEvent.click(screen.getByRole('button', { name: /theme/i }))
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('theme')).toBe('light')
    fireEvent.click(screen.getByRole('button', { name: /theme/i }))
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('theme')).toBe('dark')
  })
  it('does not throw when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    render(<ThemeToggle />)
    fireEvent.click(screen.getByRole('button', { name: /theme/i }))
    expect(document.documentElement.dataset.theme).toBe('light')
    vi.restoreAllMocks()
  })
})

const topBar = () => <QueryClientProvider client={new QueryClient()}><MemoryRouter><TopBar /></MemoryRouter></QueryClientProvider>

describe('TopBar live price', () => {
  beforeEach(() => {
    const now = Date.now()
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const body = String(url).includes('/spot')
        ? { spot_usd_oz: 2400.5, updated_at: new Date(now - 5000).toISOString(), price_source: 'x' }
        : { points: [{ t: now / 1000 - 86400, p: 2380.5 }, { t: now / 1000 - 100, p: 2399 }] }
      return { ok: true, json: async () => body }
    }))
  })
  it('shows price, 24h change and LIVE badge', async () => {
    render(topBar())
    await waitFor(() => expect(screen.getByText('$2,400.50')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText(/\+20\.00.*24h/)).toBeInTheDocument())
    expect(screen.getByText('LIVE')).toBeInTheDocument()
  })
  it('every consumer shares one poller (one /spot and one /intraday request)', async () => {
    const Probe = () => <i>{useLivePrice().price}</i>
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><TopBar /><Probe /><Probe /></MemoryRouter></QueryClientProvider>)
    await waitFor(() => expect(screen.getByText('$2,400.50')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText(/\+20\.00.*24h/)).toBeInTheDocument())
    const urls = (fetch as unknown as { mock: { calls: [string][] } }).mock.calls.map((c) => String(c[0]))
    expect(urls.filter((u) => u.includes('/spot'))).toHaveLength(1)
    expect(urls.filter((u) => u.includes('/intraday'))).toHaveLength(1)
  })
  it('a 503 from the price service shows NO PRICE AVAILABLE', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => String(url).includes('/spot')
      ? { ok: false, status: 503, json: async () => ({}) } : { ok: true, json: async () => ({ points: [] }) }))
    render(topBar())
    await waitFor(() => expect(screen.getByText('NO PRICE AVAILABLE')).toBeInTheDocument())
  })
  it('shows a connection problem when fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('x') }))
    render(topBar())
    await waitFor(() => expect(screen.getByText('CONNECTION PROBLEM')).toBeInTheDocument())
  })
})

import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { routes } from '../routes'

describe('routes', () => {
  it('redirects / to the Trade start page inside the shell with one main#page', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })))
    render(<QueryClientProvider client={new QueryClient()}><RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/'] })} /></QueryClientProvider>)
    expect(await screen.findByRole('heading', { name: 'Trade' })).toBeInTheDocument()
    expect(document.querySelectorAll('main#page')).toHaveLength(1)
    expect(screen.getByRole('link', { name: 'Trade' })).toHaveAttribute('aria-current', 'page')
  })
})
