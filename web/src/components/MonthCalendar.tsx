import type { Groups } from '../lib/periods'
import { sortedKeys } from '../lib/periods'
import { money, rtext } from '../lib/format'
import { monthName } from '../lib/time'
import MoneyText from './MoneyText'

type Props = {
  groups: Groups
  month: string
  selectedDay?: string | null
  onPickDay: (day: string) => void
  onMove: (dir: -1 | 1) => void
}

const WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** Port of btCalendarHtml: Monday-first grid; days without a closed trade are disabled. */
export default function MonthCalendar({ groups, month, selectedDay, onPickDay, onMove }: Props) {
  const r = !groups.hasUsd
  const show = (v: number) => (r ? rtext(v) : money(v))
  const [yy, mm] = month.split('-').map(Number)
  const lead = (new Date(yy, mm - 1, 1).getDay() + 6) % 7
  const nDays = new Date(yy, mm, 0).getDate()
  const all = sortedKeys(groups.months), mi = all.indexOf(month)
  const mx = groups.months.get(month)
  const dayKeys = sortedKeys(groups.days).filter((k) => k.startsWith(month))
  const green = dayKeys.filter((k) => groups.days.get(k)!.pnl > 0).length
  const red = dayKeys.filter((k) => groups.days.get(k)!.pnl < 0).length
  const nav = 'h-8 w-9 rounded bg-panel2 text-[18px] text-strong disabled:opacity-40'
  return (
    <div>
      <div className="mb-2 flex items-center gap-2.5">
        <button type="button" className={nav} disabled={mi <= 0} aria-label="Previous month with trades" onClick={() => onMove(-1)}>‹</button>
        <b className="flex-1 text-[15px] text-strong">{monthName(month)}</b>
        {mx && <MoneyText v={mx.pnl} r={r} />}
        <button type="button" className={nav} disabled={mi < 0 || mi >= all.length - 1} aria-label="Next month with trades" onClick={() => onMove(1)}>›</button>
      </div>
      <p className="mb-1.5 text-[11px] text-muted">{green} green day(s) · {red} red day(s) this month</p>
      <div className="grid grid-cols-7 gap-1" data-testid="calgrid">
        {WEEK.map((w) => <div key={w} className="text-center text-[10.5px] text-muted">{w}</div>)}
        {Array.from({ length: lead }, (_, i) => <div key={`b${i}`} data-testid="cal-blank" />)}
        {Array.from({ length: nDays }, (_, i) => {
          const dd = i + 1
          const k = `${month}-${String(dd).padStart(2, '0')}`
          const x = groups.days.get(k)
          const tone = !x ? '' : x.pnl > 0 ? 'bg-up/15' : x.pnl < 0 ? 'bg-down/15' : 'bg-panel2'
          return (
            <button key={k} type="button" data-testid="cal-day" data-day={k} disabled={!x} aria-pressed={k === selectedDay}
              aria-label={x ? `${k}: ${show(x.pnl)}, ${x.n} trades` : k} onClick={() => onPickDay(k)}
              className={`flex min-h-12 flex-col items-start gap-px rounded-md border px-1 py-1 text-left sm:min-h-14 sm:px-[5px] ${tone} ${k === selectedDay ? 'border-accent' : 'border-transparent'} ${x ? '' : 'opacity-35'}`}>
              <span className="text-[12.5px] font-bold text-text">{dd}</span>
              {x && <span className={`whitespace-nowrap text-[10px] font-bold tabular-nums sm:text-[12px] ${x.pnl > 0 ? 'text-up' : x.pnl < 0 ? 'text-down' : ''}`}>{show(x.pnl)}</span>}
              {x && <span className="hidden whitespace-nowrap text-[9.5px] text-muted sm:block">{x.n}T</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
