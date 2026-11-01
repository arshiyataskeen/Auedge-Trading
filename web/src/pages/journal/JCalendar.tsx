import { useEffect, useState } from 'react'
import type { JournalTrade } from '../../api/types'
import MoneyText from '../../components/MoneyText'
import { money } from '../../lib/format'
import { Meta, Sect, TradeTable } from './ui'

const WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const nav = 'h-8 w-9 rounded bg-panel2 text-[18px] text-strong hover:bg-hover'

/** Port of jCalendar: month grid by trading day (any month); tap a day to see its trades. */
export default function JCalendar({ days, trades, showAcc = false, onOpenTrade, resetKey }: {
  days: Record<string, { pnl: number; n?: number }>; trades: JournalTrade[]; showAcc?: boolean; onOpenTrade: (t: JournalTrade) => void
  /** changing this clears the picked day (the month is kept) */
  resetKey?: string
}) {
  const [month, setMonth] = useState(() => {
    const keys = Object.keys(days).sort()
    const d = keys.length ? new Date(keys[keys.length - 1] + 'T12:00:00') : new Date()
    return new Date(d.getFullYear(), d.getMonth(), 1)
  })
  const [sel, setSel] = useState<string | null>(null)
  useEffect(() => { setSel(null) }, [resetKey])
  const lead = (month.getDay() + 6) % 7
  const nDays = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  const ym = `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, '0')}`
  let mPnl = 0, mWin = 0, mLoss = 0
  const cells = Array.from({ length: nDays }, (_, i) => {
    const dd = i + 1, k = `${ym}-${String(dd).padStart(2, '0')}`, d = days[k]
    if (d) { mPnl += d.pnl; if (d.pnl > 0) mWin++; else if (d.pnl < 0) mLoss++ }
    return { dd, k, d }
  })
  const move = (n: number) => { setMonth(new Date(month.getFullYear(), month.getMonth() + n, 1)); setSel(null) }
  const dayTrades = sel ? trades.filter((t) => t.day === sel) : []
  return (
    <div>
      <div className="mb-1 flex items-center gap-2.5">
        <button type="button" className={nav} aria-label="Previous month" onClick={() => move(-1)}>‹</button>
        <b className="flex-1 text-center text-[15px] text-strong">{month.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</b>
        <MoneyText v={Math.round(mPnl * 100) / 100} />
        <button type="button" className={nav} aria-label="Next month" onClick={() => move(1)}>›</button>
      </div>
      <Meta cls="mb-1.5">{mWin} green day(s) · {mLoss} red day(s) this month</Meta>
      <div className="grid grid-cols-7 gap-1">
        {WEEK.map((w) => <div key={w} className="text-center text-[10.5px] text-muted">{w}</div>)}
        {Array.from({ length: lead }, (_, i) => <div key={`b${i}`} />)}
        {cells.map(({ dd, k, d }) => {
          const tone = !d ? '' : d.pnl > 0 ? 'bg-up-bg' : d.pnl < 0 ? 'bg-down-bg' : 'bg-panel2'
          return (
            <button key={k} type="button" data-testid="jcal-day" data-day={k} disabled={!d} aria-pressed={sel === k}
              aria-label={d ? `${k}: ${money(d.pnl)}, ${d.n ?? 0} trades` : k} onClick={() => setSel(sel === k ? null : k)}
              className={`flex min-h-12 flex-col items-start gap-px rounded-md border px-1 py-1 text-left sm:min-h-14 sm:px-[5px] ${tone} ${sel === k ? 'border-accent' : 'border-transparent'} ${d ? '' : 'opacity-35'}`}>
              <span className="text-[12.5px] font-bold text-text">{dd}</span>
              {d && <span className={`whitespace-nowrap text-[10px] font-bold tabular-nums sm:text-[12px] ${d.pnl > 0 ? 'text-up' : d.pnl < 0 ? 'text-down' : ''}`}>{money(Math.round(d.pnl))}</span>}
              {d && <span className="hidden text-[9.5px] text-muted sm:block">{d.n || ''}T</span>}
            </button>
          )
        })}
      </div>
      {sel ? (
        <div className="mt-3">
          <Sect>{new Date(sel + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</Sect>
          {dayTrades.length ? <TradeTable trades={dayTrades} showAcc={showAcc} onOpen={onOpenTrade} /> : <Meta>No trades.</Meta>}
        </div>
      ) : <Meta cls="mt-1.5">Tap a day to see its trades.</Meta>}
    </div>
  )
}
