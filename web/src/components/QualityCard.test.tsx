import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import QualityCard from './QualityCard'

const q = {
  score: 48, band: 'weak', avoid: true, label: 'AVOID', avoid_reasons: ['Setup quality 48/100 is below 55.'], text: '',
  factors: [
    { name: 'align', label: '1H and 15m alignment', ok: true, weight: 20, points: 20, text: 'Both point up.' },
    { name: 'news', label: 'News risk', ok: false, weight: 10, points: 0, text: 'Inside CPI window.' },
    { name: 'retest', label: '5-minute break and retest', ok: null, weight: 10, points: 5, text: 'not available' },
  ],
}

describe('QualityCard', () => {
  it('shows score, AVOID badge, factors with plain reasons and never says probability', () => {
    const { container } = render(<QualityCard q={q} />)
    expect(screen.getByText('48/100')).toBeTruthy()
    expect(screen.getByText('AVOID')).toBeTruthy()
    expect(screen.getByText('Inside CPI window.')).toBeTruthy()
    expect(screen.getByLabelText('yes')).toBeTruthy()
    expect(screen.getByLabelText('no')).toBeTruthy()
    expect(container.textContent?.toLowerCase()).not.toContain('probab')
  })
  it('renders nothing without a quality block', () => {
    const { container } = render(<QualityCard q={undefined} />)
    expect(container.textContent).toBe('')
  })
})
