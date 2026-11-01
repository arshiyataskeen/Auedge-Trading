import type { ReactNode } from 'react'
import type { JournalTrade } from '../../api/types'
import MoneyText from '../../components/MoneyText'
import { price, rtext, toneOf } from '../../lib/format'
import { Bias, Chip, TONE } from '../dashboard/Cards'
import { jDate } from './logic'

export const inputCls = 'rounded border border-line bg-app px-2 py-1 text-[12.5px] text-strong'
export const btnCls = 'rounded border border-line bg-panel2 px-3 py-1.5 text-[12.5px] text-strong hover:bg-hover disabled:opacity-50'
export const btnPrimaryCls = 'rounded border border-accent bg-accent px-3 py-1.5 text-[12.5px] font-semibold text-white hover:opacity-90 disabled:opacity-50'
export const linkBtn = 'text-[12px] text-accent underline hover:opacity-80'
export const Card = ({ children, label }: { children: ReactNode; label?: string }) =>
  <section aria-label={label} className="rounded border border-line bg-panel p-3">{children}</section>
export const Sect = ({ children }: { children: ReactNode }) => <h2 className="mb-2 text-[12px] font-semibold text-strong">{children}</h2>
export const Meta = ({ children, cls = '' }: { children: ReactNode; cls?: string }) => <div className={`text-[11.5px] text-muted ${cls}`}>{children}</div>
export const Alert = ({ children, tone = 'down' }: { children: ReactNode; tone?: 'down' | 'up' | 'warn' }) =>
  <div role={tone === 'down' ? 'alert' : undefined}
    className={`rounded px-2 py-1.5 text-[12px] ${tone === 'down' ? 'bg-down-bg text-down' : tone === 'up' ? 'bg-up-bg text-up' : 'bg-warn-bg text-warn'}`}>{children}</div>

export function Stat({ v, k, tone = '' }: { v: ReactNode; k: string; tone?: 'up' | 'dn' | '' }) {
  return (
    <div className="rounded border border-line bg-panel2 p-2">
      <div className={`text-[16px] font-semibold tabular-nums text-strong ${TONE[tone]}`}>{v}</div>
      <div className="text-[11px] text-muted">{k}</div>
    </div>
  )
}

/** Day-by-day bars (old .jday rows). */
export function DayBars({ days }: { days: { day: string; pnl: number }[] }) {
  const maxDay = Math.max(1, ...days.map((d) => Math.abs(d.pnl)))
  return (
    <div>
      {days.map((d) => (
        <div key={d.day} className="flex items-center gap-2 py-0.5 text-[12px]">
          <span className="w-[84px] shrink-0 tabular-nums text-muted">{d.day}</span>
          <span className="h-2 flex-1 overflow-hidden rounded bg-panel2">
            <i className={`block h-full ${d.pnl >= 0 ? 'bg-up' : 'bg-down'}`} style={{ width: `${Math.round((100 * Math.abs(d.pnl)) / maxDay)}%` }} />
          </span>
          <b className="w-[70px] text-right"><MoneyText v={d.pnl} /></b>
        </div>
      ))}
    </div>
  )
}

/** Trade rows (old tradeRow / tradeCard): each is a real button, so Enter / Space open the trade. */
export function TradeList({ trades, showAcc = false, onOpen }: { trades: JournalTrade[]; showAcc?: boolean; onOpen: (t: JournalTrade) => void }) {
  return (
    <div className="flex flex-col">
      {trades.map((t) => (
        <button key={t.id} type="button" data-trade={t.id} title="Open this trade" onClick={() => onOpen(t)}
          className="flex flex-wrap items-center gap-x-3 gap-y-0.5 border-b border-line px-1 py-1.5 text-left text-[12px] hover:bg-hover">
          <span className="w-[112px] tabular-nums text-muted">{jDate(t.opened_at)}</span>
          {showAcc && <span className="min-w-[110px]"><b className="text-strong">{t.account}</b> <span className="text-muted">{t.phase}</span></span>}
          <Bias kind={t.side}>{t.side}</Bias>
          {t.source === 'auedge' && <Chip>AuEdge</Chip>}
          <span className="tabular-nums">{t.lots ?? '—'} lot</span>
          <span className="tabular-nums">{price(t.entry)} → {t.exit != null ? price(t.exit) : t.net == null ? 'open' : '—'}</span>
          <span className="min-w-0 truncate text-muted">{t.setup}</span>
          {t.followed_plan === 0 && <span className="text-down">off plan</span>}
          {t.followed_plan === 1 && !showAcc && <span title="Followed the plan">✓</span>}
          <span className="text-muted">{t.emotion}</span>
          {t.planned_rr != null && <span className="tabular-nums text-muted">1:{t.planned_rr}</span>}
          {t.r != null && <span className={`tabular-nums ${TONE[toneOf(t.r)]}`}>{rtext(t.r)}</span>}
          <b className="ml-auto tabular-nums">{t.net == null ? 'open' : <MoneyText v={t.net} />}</b>
        </button>
      ))}
    </div>
  )
}
