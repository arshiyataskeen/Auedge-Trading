import type { KeyboardEvent, ReactNode } from 'react'
import type { JournalTrade } from '../../api/types'
import MoneyText from '../../components/MoneyText'
import { price, rtext } from '../../lib/format'
import { Bias, Chip, TONE } from '../dashboard/Cards'
import { jDate } from './logic'

export const inputCls = 'rounded border border-line bg-app px-2 py-1 text-[12.5px] text-strong'
export const btnCls = 'rounded border border-line bg-panel2 px-3 py-1.5 text-[12.5px] text-strong hover:bg-hover disabled:opacity-50'
export const btnPrimaryCls = 'rounded-full border border-strong bg-strong px-3 py-1.5 text-[12.5px] font-semibold text-app hover:opacity-90 disabled:opacity-50'
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

/** Small labelled field (label text above the control). */
export const Field = ({ t, children, title }: { t: string; children: ReactNode; title?: string }) =>
  <label title={title} className="flex flex-col gap-0.5 text-[11px] text-muted"><span>{t}</span>{children}</label>
/** Toggle-button class (selected / not). */
export const segCls = (on: boolean, px = 'px-2.5') =>
  `rounded border ${px} py-1 text-[12px] ${on ? 'border-accent bg-acc-bg text-strong' : 'border-line bg-panel text-muted hover:bg-hover'}`

const TH = 'whitespace-nowrap px-1.5 py-1 text-left text-[10.5px] font-normal uppercase text-muted'
const TD = 'px-1.5 py-1.5 align-middle'
const WIDE = 'hidden sm:table-cell'

/**
 * Headed trade table (old renderRecords / renderAccount / tradeRow). `showAcc`: Account column (All records, calendar of all records);
 * `plan`: Plan and Mood columns (an account's Journal tab). Rows open with a click, Enter or Space; the AuEdge chip sits under Side.
 * Under 640 px Setup, Plan, Mood and R:R plan are hidden.
 */
export function TradeTable({ trades, showAcc = false, plan = false, onOpen }: {
  trades: JournalTrade[]; showAcc?: boolean; plan?: boolean; onOpen: (t: JournalTrade) => void
}) {
  const key = (t: JournalTrade) => (e: KeyboardEvent) => {
    if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onOpen(t) }
  }
  return (
    <>
    <div className="flex flex-col sm:hidden">
      {trades.map((t) => (
        <div key={t.id} data-testid="trade-card" role="button" tabIndex={0} title="Open this trade" onClick={() => onOpen(t)} onKeyDown={key(t)}
          className="cursor-pointer border-b border-line px-1 py-2 hover:bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent">
          <div className="flex items-center gap-2 text-[12px]">
            <Bias kind={t.side}>{t.side}</Bias><b className="tabular-nums text-strong">{t.lots ?? '—'} lot</b>
            <span className="text-muted">{jDate(t.opened_at)}</span>
            <b className="ml-auto tabular-nums">{t.net == null ? 'open' : <MoneyText v={t.net} />}</b>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-1 text-[11.5px] text-muted">
            {showAcc && <span><b className="text-strong">{t.account}</b> · {t.phase || ''} ·</span>}
            <span className="tabular-nums">
              {price(t.entry)} → {t.exit != null ? price(t.exit) : '—'}
              {t.setup ? ` · ${t.setup}` : ''}{t.planned_rr != null ? ` · R:R 1:${t.planned_rr}` : ''}{t.r != null ? ` · ${rtext(t.r)}` : ''}
            </span>
            {t.followed_plan === 0 && <span className="text-down">· off plan</span>}
            {t.emotion && <span>· {t.emotion}</span>}
            {t.source === 'auedge' && <Chip>AuEdge</Chip>}
          </div>
        </div>
      ))}
    </div>
    <div className="hidden overflow-x-auto sm:block">
      <table className="w-full border-collapse text-[12px]">
        <thead>
          <tr className="border-b border-line">
            <th className={TH}>Opened</th>
            {showAcc && <th className={TH}>Account</th>}
            <th className={TH}>Side</th><th className={TH}>Lots</th><th className={TH}>Entry → exit</th>
            <th className={`${TH} ${WIDE}`}>Setup</th>
            {plan && <><th className={`${TH} ${WIDE}`}>Plan</th><th className={`${TH} ${WIDE}`}>Mood</th></>}
            <th className={`${TH} ${WIDE}`}>R:R plan</th><th className={TH}>R</th><th className={`${TH} text-right`}>Net</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id} data-trade={t.id} tabIndex={0} title="Open this trade" onClick={() => onOpen(t)}
              onKeyDown={key(t)}
              className="cursor-pointer border-b border-line hover:bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent">
              <td className={`${TD} whitespace-nowrap tabular-nums text-muted`}>{jDate(t.opened_at)}</td>
              {showAcc && <td className={TD}><b className="text-strong">{t.account}</b><div className="text-[11px] text-muted">{t.phase}</div></td>}
              <td className={TD}><Bias kind={t.side}>{t.side}</Bias>{t.source === 'auedge' && <div className="mt-0.5"><Chip>AuEdge</Chip></div>}</td>
              <td className={`${TD} tabular-nums`}>{t.lots ?? '—'}</td>
              <td className={`${TD} whitespace-nowrap tabular-nums`}>{price(t.entry)} → {t.exit != null ? price(t.exit) : t.net == null ? 'open' : '—'}</td>
              <td className={`${TD} ${WIDE} text-muted`}><span>{t.setup}</span></td>
              {plan && (
                <>
                  <td className={`${TD} ${WIDE}`}>{t.followed_plan == null ? '' : t.followed_plan ? '✓' : <span className="text-down">✕</span>}</td>
                  <td className={`${TD} ${WIDE} text-muted`}>{t.emotion}</td>
                </>
              )}
              <td className={`${TD} ${WIDE} tabular-nums text-muted`}>{t.planned_rr != null ? `1:${t.planned_rr}` : ''}</td>
              <td className={`${TD} whitespace-nowrap tabular-nums`}>{t.r != null ? rtext(t.r) : ''}</td>
              <td className={`${TD} text-right font-semibold tabular-nums`}>{t.net == null ? 'open' : <MoneyText v={t.net} />}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </>
  )
}
