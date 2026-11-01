import { describe, expect, it } from 'vitest'
import { groupTrades } from './periods'
import { localDay } from './time'

const at = (y: number, m: number, d: number, h = 12) => new Date(y, m - 1, d, h).getTime() / 1000

describe('groupTrades', () => {
  const trades = [
    { exit_t: at(2026, 5, 29), r: 1, usd: 100, balance: 10100 },
    { exit_t: at(2026, 6, 2), r: -1, usd: -50, balance: 10050 },
    { exit_t: at(2026, 6, 2, 18), r: 2, usd: 200, balance: 10250 },
  ]
  it('gives exact pnl/won/lost per month and per day', () => {
    const g = groupTrades(trades)
    expect(g.months.get('2026-05')).toEqual({ pnl: 100, n: 1, won: 1, lost: 0, idx: [0], bal: 10100 })
    expect(g.months.get('2026-06')).toEqual({ pnl: 150, n: 2, won: 1, lost: 1, idx: [1, 2], bal: 10250 })
    expect(g.days.get('2026-06-02')!.pnl).toBe(150)
    expect(g.days.get('2026-05-29')!.won).toBe(1)
    expect(g.years.get('2026')!.n).toBe(3)
    expect(g.hasUsd).toBe(true)
  })
  it('falls back to R when a trade has no dollar result', () => {
    const g = groupTrades([{ exit_t: at(2026, 6, 2), r: 1.5 }, { exit_t: at(2026, 6, 3), r: -0.5, usd: null }])
    expect(g.hasUsd).toBe(false)
    expect(g.months.get('2026-06')!.pnl).toBe(1)
    expect(g.months.get('2026-06')!.bal).toBeNull()
  })
  it('groups 5,000 trades in under 50 ms', () => {
    const many = Array.from({ length: 5000 }, (_, i) => ({ exit_t: 1.7e9 + i * 3600 * 5, r: i % 3 ? 1 : -1, usd: 10 }))
    groupTrades(many.slice(0, 50)) // warm up
    const t0 = performance.now()
    const g = groupTrades(many)
    expect(performance.now() - t0).toBeLessThan(50)
    expect(g.days.size).toBeGreaterThan(500)
    expect(localDay(many[0].exit_t)).toMatch(/^\d{4}-\d\d-\d\d$/)
  })
})
