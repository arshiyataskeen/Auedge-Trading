/** Forex-style sessions for gold. All times are wall-clock in each city, so DST is handled by Intl. */
export type SessionDef = { key: string; name: string; tz: string; open: number; close: number }
export const SESSIONS: SessionDef[] = [
  { key: 'sydney', name: 'Sydney', tz: 'Australia/Sydney', open: 7, close: 16 },
  { key: 'tokyo', name: 'Tokyo', tz: 'Asia/Tokyo', open: 9, close: 18 },
  { key: 'london', name: 'London', tz: 'Europe/London', open: 8, close: 17 },
  { key: 'newyork', name: 'New York', tz: 'America/New_York', open: 8, close: 17 },
]

const fmts = new Map<string, Intl.DateTimeFormat>()
function parts(tz: string, ms: number) {
  let f = fmts.get(tz)
  if (!f) { f = new Intl.DateTimeFormat('en-US', { timeZone: tz, weekday: 'short', hour: 'numeric', minute: 'numeric', hourCycle: 'h23' }); fmts.set(tz, f) }
  return Object.fromEntries(f.formatToParts(new Date(ms)).map((x) => [x.type, x.value])) as Record<string, string>
}

/** Gold: closed Fri 17:00 NY until Sun 18:00 NY (daily 17:00-18:00 break is not "weekend"). */
export function goldWeekendClosed(ms: number): boolean {
  const p = parts('America/New_York', ms), h = +p.hour
  return p.weekday === 'Sat' || (p.weekday === 'Fri' && h >= 17) || (p.weekday === 'Sun' && h < 18)
}

/** Is `s` open at `ms`? Needs a weekday in the city and the market not in its weekend closure. */
export function sessionOpen(s: SessionDef, ms: number): boolean {
  if (goldWeekendClosed(ms)) return false
  const p = parts(s.tz, ms)
  if (p.weekday === 'Sat' || p.weekday === 'Sun') return false
  const h = +p.hour + +p.minute / 60
  return h >= s.open && h < s.close
}

/** Seconds until `s` next flips state (opens if closed, closes if open), scanning up to 8 days. */
export function secondsToFlip(s: SessionDef, ms: number): number {
  const start = sessionOpen(s, ms), STEP = 10 * 60e3
  const t0 = Math.floor(ms / 60e3) * 60e3
  for (let t = t0 + STEP; t <= t0 + 8 * 86400e3; t += STEP) {
    if (sessionOpen(s, t) !== start) {
      for (let u = t - STEP + 60e3; u <= t; u += 60e3) if (sessionOpen(s, u) !== start) return Math.max(0, (u - ms) / 1000)
      return (t - ms) / 1000
    }
  }
  return Infinity
}

export function sessionStatuses(ms: number) {
  return SESSIONS.map((s) => ({ ...s, isOpen: sessionOpen(s, ms), flipIn: secondsToFlip(s, ms) }))
}

/** "2d 3h" / "3h 5m" / "12m". */
export function span(sec: number): string {
  const m = Math.max(0, Math.round(sec / 60)), d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60
  if (d) return `${d}d ${h}h`
  if (h) return `${h}h ${mm}m`
  return `${mm}m`
}

/** Upcoming High-impact events, soonest first (USD only when currency known). */
export function upcomingHigh<T extends { t: number; impact: string; name: string }>(events: T[] | undefined, nowSec: number, max = 12): T[] {
  return (events ?? []).filter((e) => e.impact === 'High' && e.t > nowSec).sort((a, b) => a.t - b.t).slice(0, max)
}
