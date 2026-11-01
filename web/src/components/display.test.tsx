import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import { getJSON } from '../api/client'
import QueryCard from './QueryCard'
import MoneyText from './MoneyText'
import SummaryCard from './SummaryCard'
import EquityChart from './EquityChart'

afterEach(() => vi.unstubAllGlobals())

function Probe() {
  const q = useQuery({ queryKey: ['p'], queryFn: () => getJSON<{ v: string }>('/api/p'), retry: false })
  return <QueryCard query={q} title="Probe">{(d) => <p>value {d.v}</p>}</QueryCard>
}

it('QueryCard shows error and retries', async () => {
  const f = vi.fn()
    .mockResolvedValueOnce(new Response('x', { status: 500 }))
    .mockResolvedValueOnce(new Response('{"v":"hello"}', { status: 200 }))
  vi.stubGlobal('fetch', f)
  render(<QueryClientProvider client={new QueryClient()}><Probe /></QueryClientProvider>)
  expect(screen.getByTestId('loading-card')).toHaveStyle({ minHeight: '120px' })
  expect(await screen.findByText(/HTTP 500/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  await waitFor(() => expect(screen.getByText('value hello')).toBeInTheDocument())
})

it('MoneyText tone classes', () => {
  const { rerender } = render(<MoneyText v={12} />)
  expect(screen.getByText('+$12')).toHaveClass('text-up', 'tabular-nums')
  rerender(<MoneyText v={-5} />)
  expect(screen.getByText('−$5')).toHaveClass('text-down')
  rerender(<MoneyText v={0} />)
  expect(screen.getByText('$0')).not.toHaveClass('text-up')
  rerender(<MoneyText v={1.5} r />)
  expect(screen.getByText('+1.50R')).toHaveClass('text-up')
})

it('SummaryCard renders label/value pairs', () => {
  render(<SummaryCard title="T" items={[{ label: 'Trades', value: 5 }, { label: 'Win', value: '60%' }]} />)
  expect(screen.getByText('Trades').nextSibling).toHaveTextContent('5')
  expect(screen.getByText('Win').nextSibling).toHaveTextContent('60%')
})

it('EquityChart draws a polyline with N+1 points', () => {
  const { container } = render(<EquityChart curve={[[1, 1], [2, -1], [3, 2]]} />)
  const pl = container.querySelector('polyline')!
  expect(pl.getAttribute('points')!.trim().split(' ')).toHaveLength(4)
  expect(screen.getByText(/3 trades/)).toBeInTheDocument()
})
