import { useState } from 'react'
import { useCalendar } from '../../api/endpoints'
import MoneyText from '../../components/MoneyText'
import QueryCard from '../../components/QueryCard'
import { money } from '../../lib/format'
import { card } from '../backtest/ui'
import DayDetail from './DayDetail'

const WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const pad = (n: number) => String(n).padStart(2, '0')
const ymdLocal = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const monthKey = (y: number, m0: number) => `${y}-${pad(m0 + 1)}`

/** Port of loadCalendar + renderCalendar: month grid of demo P&L per local day; a day opens its detail below. */
export default function CalendarPanel() {
  const q = useCalendar()
  const [month, setMonth] = useState<string | null>(null) // null: month of the newest day with data
  const [sel, setSel] = useState<string | null>(null)

  return (
    <QueryCard query={q} title="Calendar">
      {({ days }) => {
        const keys = Object.keys(days).sort()
        const base = month ?? (keys.length ? keys[keys.length - 1].slice(0, 7) : monthKey(new Date().getFullYear(), new Date().getMonth()))
        const [yy, mm] = base.split('-').map(Number)
        const first = new Date(yy, mm - 1, 1)
        const lead = (first.getDay() + 6) % 7
        const nDays = new Date(yy, mm, 0).getDate()
        const today = ymdLocal(new Date())
        const monthPnl = Object.entries(days).filter(([k]) => k.startsWith(base)).reduce((a, [, d]) => a + d.pnl, 0)
        const move = (dir: number) => { const d = new Date(yy, mm - 1 + dir, 1); setMonth(monthKey(d.getFullYear(), d.getMonth())) }
        const nav = 'h-8 w-9 rounded bg-panel2 text-[18px] text-strong'
        return (
          <div className="flex flex-col gap-3">
            <section className={card} aria-label="Demo calendar">
              <div className="mb-2 flex items-center gap-2.5">
                <button type="button" className={nav} aria-label="Previous month" onClick={() => move(-1)}>‹</button>
                <b className="flex-1 text-[15px] text-strong">{first.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</b>
                <MoneyText v={monthPnl} />
                <button type="button" className={nav} aria-label="Next month" onClick={() => move(1)}>›</button>
              </div>
              <div className="grid grid-cols-7 gap-1" data-testid="calgrid">
                {WEEK.map((w) => <div key={w} className="text-center text-[10.5px] text-muted">{w}</div>)}
                {Array.from({ length: lead }, (_, i) => <div key={`b${i}`} />)}
                {Array.from({ length: nDays }, (_, i) => {
                  const dd = i + 1
                  const k = `${base}-${pad(dd)}`
                  const x = days[k]
                  const tone = !x ? '' : x.pnl > 0 ? 'bg-up-bg' : x.pnl < 0 ? 'bg-down-bg' : 'bg-panel2'
                  const tag = `${x?.trades ? x.trades + 'T' : ''}${x?.live ? ' live' : x?.sim ? ' sim' : ''}`.trim()
                  return (
                    <button key={k} type="button" data-day={k} disabled={!x} aria-pressed={k === sel}
                      aria-label={x ? `${k}: ${x.trades ? money(x.pnl) : 'no trades'}, ${x.trades} trades` : k} onClick={() => setSel(k)}
                      className={`flex min-h-12 flex-col items-start gap-px rounded-md border px-1 py-1 text-left sm:min-h-14 sm:px-[5px] ${tone} ${k === sel ? 'border-accent' : k === today ? 'border-line2' : 'border-transparent'} ${x ? '' : 'opacity-35'}`}>
                      <span className="text-[12.5px] font-bold text-text">{dd}</span>
                      {x && (
                        <span className={`whitespace-nowrap text-[10px] font-bold tabular-nums sm:text-[12px] ${x.pnl > 0 ? 'text-up' : x.pnl < 0 ? 'text-down' : ''}`}>
                          {x.trades ? money(x.pnl) : '·'}
                        </span>
                      )}
                      {x && tag && <span className="hidden whitespace-nowrap text-[9.5px] text-muted sm:block">{tag}</span>}
                    </button>
                  )
                })}
              </div>
              <p className="mt-2 text-[11px] text-muted">
                Green / red = demo profit or loss that day (0.1 lot). <b>live</b> = real-time demo, <b>sim</b> = the simulated last month.
                Tap a day for its calls, agents, levels and trades.
              </p>
            </section>
            {sel && <DayDetail date={sel} />}
          </div>
        )
      }}
    </QueryCard>
  )
}
