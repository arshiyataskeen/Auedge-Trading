import { render, screen, within } from '@testing-library/react'
import { expect, it } from 'vitest'
import NewsIntelCard from './NewsIntelCard'

const base = { phase: 'pre', event: { kind: 'NFP', name: 'Nonfarm Payrolls', t: 1793000000 }, others: [], expected_move: 18.4,
  expected_range: [4060.5, 4097.25], probs: { down: 0.3, side: 0.4, up: 0.3 }, similar: [], uncertain: false, notes: [], mode: 'advisory' }
const post = { ...base, phase: 'post', surprise_z: 1.4, similar: [
  { date: '2026-05-01', kind: 'NFP', z: 1.2, move60: 21.5, label: 'up' }, { date: '2026-04-03', kind: 'NFP', z: -0.8, move60: -9.25, label: 'down' }] }

it('no news: plain message, no chances', () => {
  render(<NewsIntelCard extra={{ phase: 'none', mode: 'advisory', notes: [] }} />)
  expect(screen.getByText(/No major US release/)).toBeTruthy()
  expect(screen.queryByText(/Chances/)).toBeNull()
})
it('missing extra: unavailable message, no crash', () => {
  render(<NewsIntelCard extra={undefined} />)
  expect(screen.getByText(/News intelligence is not available/)).toBeTruthy()
})
it('pre: event, typical move (never forecast), range, advisory chances, M5 chips, Claude note', () => {
  render(<NewsIntelCard extra={{ ...base, note: 'Quiet before the storm.', m5: { bos: 'up', retest: 'done', text: 'M5 broke up' } }} />)
  expect(screen.getByText('Nonfarm Payrolls')).toBeTruthy()
  expect(screen.getByText('Typical first-hour move')).toBeTruthy()
  expect(screen.queryByText(/forecast/i)).toBeNull()
  expect(screen.getByText(/\$18/)).toBeTruthy()
  expect(screen.getByText(/4,060\.50/)).toBeTruthy()
  expect(screen.getByText('Chances (advisory — not used for trades)')).toBeTruthy()
  expect(screen.getByLabelText('down 30%, flat 40%, up 30%')).toBeTruthy()
  expect(screen.getByText('Quiet before the storm.')).toBeTruthy()
  expect(screen.getByText('M5 broke up')).toBeTruthy()
  expect(screen.queryByText('AVOID')).toBeNull()
})
it('live mode drops the advisory wording; avoid shows the badge', () => {
  render(<NewsIntelCard avoid extra={{ ...base, mode: 'live' }} />)
  expect(screen.getByText('Chances')).toBeTruthy()
  expect(screen.getByText('AVOID')).toBeTruthy()
})
it('post: surprise and similar releases table', () => {
  render(<NewsIntelCard extra={post} />)
  expect(screen.getByText('+1.4')).toBeTruthy()
  const rows = screen.getAllByTestId('similar-row')
  expect(rows).toHaveLength(2)
  expect(within(rows[0]).getByText('2026-05-01')).toBeTruthy()
  expect(within(rows[0]).getByText('+1.2')).toBeTruthy()
  expect(within(rows[0]).getByText('+$22')).toBeTruthy()
  expect(within(rows[1]).getByText('−$9')).toBeTruthy()
})
it('uncertain is flagged; compact hides the table', () => {
  render(<NewsIntelCard compact extra={{ ...post, uncertain: true }} />)
  expect(screen.getAllByText(/uncertain/i).length).toBeGreaterThan(0)
  expect(screen.queryByTestId('similar-row')).toBeNull()
  expect(screen.getByText('Typical first-hour move')).toBeTruthy()
})

it('fix round: bad range hidden, m5_ratio shown, region focusable, compact note fallback, chances sum to 100', () => {
  const { unmount } = render(<NewsIntelCard extra={{ ...post, expected_range: [null, 5], m5_ratio: 1.84, probs: { down: 0.333, side: 0.333, up: 0.334 } }} />)
  expect(screen.queryByText(/range/)).toBeNull()
  expect(screen.getByText('M5 candle size vs normal: 1.8×')).toBeTruthy()
  const region = screen.getByRole('region', { name: 'Similar past releases' })
  expect(region.getAttribute('tabindex')).toBe('0')
  expect(screen.getByLabelText('down 33%, flat 33%, up 34%')).toBeTruthy()
  unmount()
  render(<NewsIntelCard compact extra={{ ...base, expected_move: null, notes: ['Models are stale.', 'second'] }} />)
  expect(screen.getByText('Models are stale.')).toBeTruthy()
  expect(screen.queryByText('second')).toBeNull()
})
