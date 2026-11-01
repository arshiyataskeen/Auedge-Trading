import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { BtTrade } from '../api/types'
import { groupTrades } from '../lib/periods'
import MonthCalendar from './MonthCalendar'
import MonthTable from './MonthTable'
import DayTrades from './DayTrades'
import TradeReplay from './TradeReplay'

const m = vi.hoisted(() => {
  const series = { setData: vi.fn(), setMarkers: vi.fn(), createPriceLine: vi.fn() }
  const chart = {
    addCandlestickSeries: vi.fn(() => series), remove: vi.fn(),
    timeScale: vi.fn(() => ({ setVisibleLogicalRange: vi.fn() })),
  }
  return { series, chart, createChart: vi.fn(() => chart) }
})
vi.mock('lightweight-charts', () => ({
  createChart: m.createChart,
  CrosshairMode: { Normal: 0 },
  LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
}))

const T0 = Math.floor(new Date(2026, 5, 2, 10).getTime() / 1000)
const trade: BtTrade = {
  side: 'BUY', kind: 'plan', decided_t: T0, entry_t: T0 + 900, entry: 2000, stop: 1990, t1: 2020,
  exit_t: T0 + 900 * 5, exit: 2020, why: 'target', r: 2, usd: 200,
}
const candles = (n: number) => ({
  tf: '15m', sec: 900, candles: Array.from({ length: n }, (_, i) => ({ t: T0 - 900 * 4 + 900 * i, o: 2000, h: 2005, l: 1995, c: 2000 + i })),
})

function mount(ui: React.ReactElement) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>)
}
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })

beforeEach(() => { vi.clearAllMocks() })
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

it('calendar for 2026-06 has 0 leading blanks and 30 day cells, disabled without trades', () => {
  const g = groupTrades([{ exit_t: T0, r: 1, usd: 100 }, { exit_t: T0 + 86400 * 3, r: -1, usd: -40 }])
  const onPickDay = vi.fn()
  render(<MonthCalendar groups={g} month="2026-06" onPickDay={onPickDay} onMove={() => {}} />)
  expect(screen.queryAllByTestId('cal-blank')).toHaveLength(0)
  const days = screen.getAllByTestId('cal-day')
  expect(days).toHaveLength(30)
  expect(days.filter((d) => !(d as HTMLButtonElement).disabled)).toHaveLength(2)
  expect(screen.getByText('+$100')).toBeInTheDocument()
  fireEvent.click(days[1])
  expect(onPickDay).toHaveBeenCalledWith('2026-06-02')
})

it('calendar offsets the first day to Monday-first and disables month arrows at the ends', () => {
  const g = groupTrades([{ exit_t: Math.floor(new Date(2026, 6, 15, 12).getTime() / 1000), r: 1 }])
  const onMove = vi.fn()
  render(<MonthCalendar groups={g} month="2026-07" onPickDay={() => {}} onMove={onMove} />)
  expect(screen.getAllByTestId('cal-blank')).toHaveLength(2) // July 1, 2026 is a Wednesday
  expect(screen.getByLabelText('Previous month with trades')).toBeDisabled()
  expect(screen.getByLabelText('Next month with trades')).toBeDisabled()
  expect(screen.getAllByText('+1.00R')).toHaveLength(2)
})

it('month table lists months, totals and picks a month', () => {
  const g = groupTrades([
    { exit_t: Math.floor(new Date(2026, 4, 29, 12).getTime() / 1000), r: 1, usd: 100, balance: 10100 },
    { exit_t: T0, r: -1, usd: -50, balance: 10050 },
  ])
  const onPick = vi.fn()
  render(<MonthTable groups={g} year="2026" onPick={onPick} />)
  expect(screen.getByText('2026 total')).toBeInTheDocument()
  expect(screen.getAllByText('$10,050')).toHaveLength(2)
  fireEvent.click(screen.getByText('June 2026'))
  expect(onPick).toHaveBeenCalledWith('2026-06')
})

it('day trades rows call onReplay with the trade index', () => {
  const onReplay = vi.fn()
  render(<DayTrades trades={[trade, { ...trade, r: -1, usd: -50 }]} idx={[1]} onReplay={onReplay} />)
  fireEvent.click(screen.getByTitle('Click to replay'))
  expect(onReplay).toHaveBeenCalledWith(1)
})

it('replay requests src=backup and builds chart, price lines and markers', async () => {
  const f = vi.fn().mockResolvedValue(json(candles(12)))
  vi.stubGlobal('fetch', f)
  mount(<TradeReplay trade={trade} src="backup" onClose={() => {}} />)
  await waitFor(() => expect(m.createChart).toHaveBeenCalled())
  expect(f.mock.calls[0][0]).toContain('/api/backtest/candles?start=')
  expect(f.mock.calls[0][0]).toContain('&src=backup')
  expect(m.series.createPriceLine.mock.calls.map((c) => c[0].title)).toEqual(['ENTRY', 'STOP', 'HALF @1R', 'TARGET'])
  expect(m.series.createPriceLine.mock.calls[2][0]).toMatchObject({ price: 2010, lineStyle: 1 })
  const markers = m.series.setMarkers.mock.calls.at(-1)![0]
  expect(markers.map((x: { text: string }) => x.text)).toEqual(['IN 2,000.00', 'OUT 2,020.00'])
  expect(m.series.setData.mock.calls.at(-1)![0]).toHaveLength(12)
})

it('replay omits src when not given', async () => {
  const f = vi.fn().mockResolvedValue(json(candles(3)))
  vi.stubGlobal('fetch', f)
  mount(<TradeReplay trade={trade} onClose={() => {}} />)
  await waitFor(() => expect(f).toHaveBeenCalled())
  expect(f.mock.calls[0][0]).not.toContain('src=')
})

it('replay shows "No candles" on an empty response and the server error text on error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ tf: '15m', sec: 900, candles: [] })))
  const a = mount(<TradeReplay trade={trade} onClose={() => {}} />)
  expect(await screen.findByText('No candles for this trade.')).toBeInTheDocument()
  expect(m.createChart).not.toHaveBeenCalled()
  a.unmount()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ error: 'backup offline' })))
  mount(<TradeReplay trade={{ ...trade, entry_t: trade.entry_t + 1 }} onClose={() => {}} />)
  expect(await screen.findByText('backup offline')).toBeInTheDocument()
})

it('controls: step, slider, play at the chosen speed, stops at the end, removes chart on unmount', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(candles(12))))
  const { unmount } = mount(<TradeReplay trade={{ ...trade, entry_t: trade.entry_t + 2 }} onClose={() => {}} />)
  await waitFor(() => expect(m.createChart).toHaveBeenCalled())
  const len = () => m.series.setData.mock.calls.at(-1)![0].length
  const slider = screen.getByLabelText('Replay position') as HTMLInputElement
  expect(slider.max).toBe('12')
  fireEvent.click(screen.getByLabelText('Step back'))
  await waitFor(() => expect(len()).toBe(11))
  fireEvent.click(screen.getByLabelText('Step forward'))
  await waitFor(() => expect(len()).toBe(12))
  fireEvent.change(slider, { target: { value: '3' } })
  await waitFor(() => expect(len()).toBe(3))
  expect(screen.getByLabelText('Replay speed')).toHaveDisplayValue('Normal')
  const opts = [...(screen.getByLabelText('Replay speed') as HTMLSelectElement).options].map((o) => [o.text, o.value])
  expect(opts).toEqual([['Slow', '800'], ['Normal', '400'], ['Fast', '150']])

  vi.useFakeTimers()
  fireEvent.change(screen.getByLabelText('Replay speed'), { target: { value: '150' } })
  fireEvent.click(screen.getByRole('button', { name: '▶ Play' }))
  expect(screen.getByRole('button', { name: '⏸ Pause' })).toBeInTheDocument()
  act(() => { vi.advanceTimersByTime(150) })
  expect(len()).toBe(4)
  act(() => { vi.advanceTimersByTime(150 * 20) })
  expect(len()).toBe(12)
  expect(screen.getByRole('button', { name: '▶ Play' })).toBeInTheDocument()
  expect(vi.getTimerCount()).toBe(0)
  // Play at the end restarts from the entry candle, then pausing clears the timer
  fireEvent.click(screen.getByRole('button', { name: '▶ Play' }))
  expect(len()).toBe(6) // entry candle index (1-based)
  fireEvent.click(screen.getByRole('button', { name: '⏸ Pause' }))
  expect(vi.getTimerCount()).toBe(0)
  unmount()
  expect(m.chart.remove).toHaveBeenCalled()
})

it('replay is closable with Escape and keeps focus inside', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(candles(5))))
  const onClose = vi.fn()
  mount(<TradeReplay trade={trade} onClose={onClose} />)
  await waitFor(() => expect(m.createChart).toHaveBeenCalled())
  const dlg = screen.getByRole('dialog')
  expect(dlg).toHaveAttribute('aria-modal', 'true')
  const close = screen.getByLabelText('Close replay')
  expect(close).toHaveFocus()
  fireEvent.keyDown(close, { key: 'Tab', shiftKey: true })
  expect(dlg.contains(document.activeElement)).toBe(true)
  expect(close).not.toHaveFocus() // wrapped to the last control
  fireEvent.keyDown(document.activeElement!, { key: 'Tab' })
  expect(close).toHaveFocus()
  fireEvent.keyDown(close, { key: 'Escape' })
  expect(onClose).toHaveBeenCalledTimes(1)
})
