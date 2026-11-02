import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { Analysis } from '../../api/types'
import { FlowView } from './Flow'

const ag = (agent: string, o = {}) => ({ agent, status: 'OK', bias: 'BUY', bias_label: 'BUY', confidence: 60, label: agent, rows: [], reasons: [], warnings: [], levels: [], metrics: {}, summary: '', headline: '', subtitle: '', timeframe: '1h', veto: false, ...o })
const D = (g: string) => ({ generated_at: g, perf_weights_on: false, track: null,
  agents: [ag('wyckoff'), ag('stophunt', { vote_off: true }), ag('skeptic'), ag('psychology')],
  chief: { bias: 'WAIT', confidence: 50, quality: { score: 40, band: 'weak', avoid: true }, plan: { action: 'NO TRADE', stop: null } } }) as unknown as Analysis
const mm = (m: boolean) => vi.stubGlobal('matchMedia', () => ({ matches: m, addEventListener() {}, removeEventListener() {} }))
afterEach(() => vi.unstubAllGlobals())

it('renders a node per agent and greys off votes', () => {
  mm(false)
  render(<FlowView d={D('a')} flags={[{ name: 'ALIGN', on: false, text: '' }]} demo={undefined} />)
  expect(document.querySelectorAll('[data-id=wyckoff]')).toHaveLength(1)
  expect(document.querySelector('[data-id=stophunt]')).toHaveAttribute('data-off', 'true')
  expect(document.querySelector('[data-id=flag-ALIGN]')).toBeTruthy()
  expect(screen.getByText('Waiting')).toBeInTheDocument()
})
it('replay restarts on new generated_at and on button', () => {
  mm(false)
  const { rerender } = render(<FlowView d={D('a')} flags={[]} demo={undefined} />)
  expect(screen.getByTestId('flow')).toHaveAttribute('data-run', '0')
  rerender(<FlowView d={D('b')} flags={[]} demo={undefined} />)
  expect(screen.getByTestId('flow')).toHaveAttribute('data-run', '1')
  act(() => { fireEvent.click(screen.getByText('Replay')) })
  expect(screen.getByTestId('flow')).toHaveAttribute('data-run', '2')
})
it('is static with reduced motion', () => {
  mm(true)
  render(<FlowView d={D('a')} flags={[]} demo={undefined} />)
  expect(screen.getByTestId('flow')).toHaveAttribute('data-static', 'true')
  expect(document.querySelector('.flow-dot')).toBeNull()
})
