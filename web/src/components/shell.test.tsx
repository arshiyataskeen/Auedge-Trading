import { useState } from 'react'
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Sidebar from './Sidebar'
import Tabs from './Tabs'
import ThemeToggle from './ThemeToggle'
import TopBar from './TopBar'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); delete document.documentElement.dataset.theme })

describe('Sidebar', () => {
  it('renders the 7 items in order and marks the current route', () => {
    render(<MemoryRouter initialEntries={['/journal/3']}><Sidebar /></MemoryRouter>)
    const links = screen.getAllByRole('link')
    expect(links.map((l) => l.textContent)).toEqual(['Dashboard', 'Trade', 'Backtest', 'Journal', 'Demo', 'News', 'Agents'])
    const cur = links.filter((l) => l.getAttribute('aria-current') === 'page')
    expect(cur).toHaveLength(1)
    expect(cur[0].textContent).toBe('Journal')
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
    render(<MemoryRouter><TopBar /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('$2,400.50')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText(/\+20\.00.*24h/)).toBeInTheDocument())
    expect(screen.getByText('LIVE')).toBeInTheDocument()
  })
  it('shows a connection problem when fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('x') }))
    render(<MemoryRouter><TopBar /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('CONNECTION PROBLEM')).toBeInTheDocument())
  })
})

import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { routes } from '../routes'

describe('routes', () => {
  it('redirects / to the dashboard inside the shell with one main#page', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })))
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/'] })} />)
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(document.querySelectorAll('main#page')).toHaveLength(1)
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page')
  })
})
