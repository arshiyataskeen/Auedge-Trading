import { describe, expect, it } from 'vitest'
import { countdown, localDay, localMonth, marketStatus, monthName, nyTradingDay } from './time'

const utc = (s: string) => Date.parse(s)

// verbatim old cdText from static/index.html
function oldCd(sec: number) {
  const a = Math.abs(sec), d = Math.floor(a / 86400), h = Math.floor(a % 86400 / 3600), m = Math.floor(a % 3600 / 60)
  const t = d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`
  return sec >= 0 ? `in ${t}` : `${t} ago`
}

describe('nyTradingDay across DST', () => {
  it('spring forward 2026-03-08', () => {
    // EDT from 02:00 that day: 17:59 EDT = 21:59Z, 18:00 EDT = 22:00Z
    const a = nyTradingDay(utc('2026-03-08T21:59:00Z') / 1000)
    const b = nyTradingDay(utc('2026-03-08T22:00:00Z') / 1000)
    expect(a).toBe('2026-03-08')
    expect(b).toBe('2026-03-09')
  })
  it('fall back 2026-11-01', () => {
    // EST: 17:59 = 22:59Z, 18:00 = 23:00Z
    expect(nyTradingDay(utc('2026-11-01T22:59:00Z') / 1000)).toBe('2026-11-01')
    expect(nyTradingDay(utc('2026-11-01T23:00:00Z') / 1000)).toBe('2026-11-02')
  })
  it('matches old +6h shift on ordinary days', () => {
    const t = utc('2026-06-10T23:30:00Z')
    const p = new Date(t + 6 * 3600e3)
    const old = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).format(p)
    expect(nyTradingDay(t / 1000)).toBe(old)
  })
})

describe('marketStatus', () => {
  it('Friday 17:00 NY closed', () => {
    // 2026-06-12 is Friday; 17:00 EDT = 21:00Z
    expect(marketStatus(utc('2026-06-12T21:00:00Z')).open).toBe(false)
    expect(marketStatus(utc('2026-06-12T21:00:00Z')).reason).toBe('weekend')
    expect(marketStatus(utc('2026-06-12T20:59:00Z')).open).toBe(true)
  })
  it('Sunday 18:00 NY open, 17:59 closed', () => {
    expect(marketStatus(utc('2026-06-14T22:00:00Z')).open).toBe(true)
    expect(marketStatus(utc('2026-06-14T21:59:00Z')).open).toBe(false)
  })
  it('Saturday closed', () => {
    expect(marketStatus(utc('2026-06-13T15:00:00Z')).open).toBe(false)
  })
  it('daily break 17:xx NY Mon-Thu', () => {
    const s = marketStatus(utc('2026-06-10T21:30:00Z'))
    expect(s.open).toBe(false)
    expect(s.reason).toBe('daily break')
    expect(marketStatus(utc('2026-06-10T22:00:00Z')).open).toBe(true)
  })
})

describe('countdown', () => {
  it('matches old cdText', () => {
    for (const s of [3725, 0, 59, 60, 3600, 86400, 90061, -3725, -30, -172800])
      expect(countdown(s)).toBe(oldCd(s))
    expect(countdown(3725)).toBe('in 1h 2m')
  })
})

describe('local dates', () => {
  it('localDay/localMonth use local time', () => {
    const ts = new Date(2026, 2, 5, 23, 30).getTime() / 1000
    expect(localDay(ts)).toBe('2026-03-05')
    expect(localMonth(ts)).toBe('2026-03')
  })
  it('monthName', () => {
    expect(monthName('2026-03')).toBe('March 2026')
  })
})
