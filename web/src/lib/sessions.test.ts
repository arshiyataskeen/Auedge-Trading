import { describe, expect, it } from 'vitest'
import { goldWeekendClosed, sessionOpen, SESSIONS, span, upcomingHigh, secondsToFlip } from './sessions'

const S = (k: string) => SESSIONS.find((s) => s.key === k)!
describe('sessions', () => {
  it('London winter 08:00 UTC open, 07:00 UTC closed; summer shifts by DST', () => {
    expect(sessionOpen(S('london'), Date.UTC(2026, 0, 14, 8, 0))).toBe(true)
    expect(sessionOpen(S('london'), Date.UTC(2026, 0, 14, 7, 59))).toBe(false)
    expect(sessionOpen(S('london'), Date.UTC(2026, 6, 15, 7, 0))).toBe(true)   // 08:00 BST
    expect(sessionOpen(S('london'), Date.UTC(2026, 6, 15, 6, 59))).toBe(false)
  })
  it('New York 08:00 local, DST aware', () => {
    expect(sessionOpen(S('newyork'), Date.UTC(2026, 0, 14, 13, 0))).toBe(true)
    expect(sessionOpen(S('newyork'), Date.UTC(2026, 6, 15, 12, 0))).toBe(true)
    expect(sessionOpen(S('newyork'), Date.UTC(2026, 6, 15, 11, 59))).toBe(false)
  })
  it('gold weekend: Fri 17:00 NY to Sun 18:00 NY', () => {
    expect(goldWeekendClosed(Date.UTC(2026, 0, 16, 21, 59))).toBe(false)   // Fri 16:59 NY
    expect(goldWeekendClosed(Date.UTC(2026, 0, 16, 22, 0))).toBe(true)
    expect(goldWeekendClosed(Date.UTC(2026, 0, 18, 22, 59))).toBe(true)    // Sun 17:59 NY
    expect(goldWeekendClosed(Date.UTC(2026, 0, 18, 23, 0))).toBe(false)
    expect(sessionOpen(S('tokyo'), Date.UTC(2026, 0, 17, 1, 0))).toBe(false) // Sat
  })
  it('flip countdown', () => {
    expect(secondsToFlip(S('london'), Date.UTC(2026, 0, 14, 16, 0))).toBe(3600)
    expect(secondsToFlip(S('london'), Date.UTC(2026, 0, 14, 7, 0))).toBe(3600)
  })
  it('span + upcomingHigh', () => {
    expect(span(2 * 86400 + 3 * 3600)).toBe('2d 3h')
    expect(span(3 * 3600 + 5 * 60)).toBe('3h 5m')
    expect(span(720)).toBe('12m')
    const ev = [{ t: 50, impact: 'High', name: 'b' }, { t: 10, impact: 'High', name: 'a' }, { t: 20, impact: 'Low', name: 'x' }, { t: -5, impact: 'High', name: 'old' }]
    expect(upcomingHigh(ev, 0).map((e) => e.name)).toEqual(['a', 'b'])
  })
})
