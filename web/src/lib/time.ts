const NY = 'America/New_York'
const pad = (n: number) => String(n).padStart(2, '0')

/** Local (browser timezone) day YYYY-MM-DD of an epoch-seconds timestamp. */
export function localDay(ts: number): string {
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function localMonth(ts: number): string {
  return localDay(ts).slice(0, 7)
}

export function monthName(key: string): string {
  const [y, m] = key.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleString('en-US', { month: 'long', year: 'numeric' })
}

const nyParts = new Intl.DateTimeFormat('en-US', {
  timeZone: NY, year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short', hour: 'numeric', hourCycle: 'h23',
})

function ny(ms: number) {
  return Object.fromEntries(nyParts.formatToParts(new Date(ms)).map((x) => [x.type, x.value])) as Record<string, string>
}

/**
 * Gold trading day: session runs 18:00 NY -> 17:00 NY and is named by its end day,
 * so from 18:00 NY onward the day is the next calendar day. `ts` is epoch seconds.
 */
export function nyTradingDay(ts: number): string {
  const p = ny(ts * 1000)
  let date = Date.UTC(+p.year, +p.month - 1, +p.day)
  if (+p.hour >= 18) date += 86400e3
  const d = new Date(date)
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`
}

/** Port of the old marketStatus; `nowMs` is epoch milliseconds. */
export function marketStatus(nowMs: number): { open: boolean; reason?: string } {
  const p = ny(nowMs)
  const wd = p.weekday, h = +p.hour
  if (wd === 'Sat' || (wd === 'Fri' && h >= 17) || (wd === 'Sun' && h < 18)) return { open: false, reason: 'weekend' }
  if (h === 17) return { open: false, reason: 'daily break' }
  return { open: true }
}

/** Port of the old cdText: "in 1h 2m" / "3m ago". */
export function countdown(sec: number): string {
  const a = Math.abs(sec), d = Math.floor(a / 86400), h = Math.floor((a % 86400) / 3600), m = Math.floor((a % 3600) / 60)
  const t = d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`
  return sec >= 0 ? `in ${t}` : `${t} ago`
}
