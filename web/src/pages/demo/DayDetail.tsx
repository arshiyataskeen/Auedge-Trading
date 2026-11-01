import { useState } from 'react'
import { useCalendarDay } from '../../api/endpoints'
import type { BtStep, CalendarDayDetail } from '../../api/types'
import MoneyText from '../../components/MoneyText'
import QueryCard from '../../components/QueryCard'
import TradeReplay from '../../components/TradeReplay'
import { price } from '../../lib/format'
import { btn, card, LABELS, sect } from '../backtest/ui'
import DayReplay from './DayReplay'
import { hm } from './logic'

const niceDate = (date: string) =>
  new Date(date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })

const tone = (a: { a: string; sd: string | null }) =>
  /NOW/.test(a.a) ? (a.sd === 'BUY' ? 'text-up' : 'text-down') : /WATCH/.test(a.a) ? 'text-muted' : 'text-warn'

/** Port of loadDay + renderDay: the Chief's calls, demo trades, agents and levels for one local date. */
export default function DayDetail({ date }: { date: string }) {
  const q = useCalendarDay(date)
  return (
    <div className="min-h-[200px]">
      <QueryCard query={q} title="Day detail">
        {(d) => (d.error ? <div role="alert" className={`${card} text-[12.5px] text-warn`}>{d.error}</div> : <Body d={d} />)}
      </QueryCard>
    </div>
  )
}

function Body({ d }: { d: CalendarDayDetail }) {
  const [replay, setReplay] = useState<number | null>(null)
  const [whole, setWhole] = useState(false)
  const tmIn = (ts: number) => (ts < d.window[0]
    ? new Date(ts * 1000).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : hm(ts))
  const agents = Object.entries(d.agents).sort((x, y) => y[1].calls - x[1].calls)
  const live = d.source === 'live'

  const levels = (st: BtStep | null | undefined) => {
    if (!st) return <p className="text-[12px] text-muted">No analysis saved for this day.</p>
    const rows: [string, string][] = [
      ['Time · price', `${hm(st.t)} · ${price(st.p)}`],
      ['Trend', st.tr || '—'],
      ['Plan', st.a],
    ]
    if (st.lv && st.lv[2] != null) rows.push(['Entry · stop · 1R · target', `${price(((st.lv[0] ?? 0) + (st.lv[1] ?? 0)) / 2)} · ${price(st.lv[2])} · ${price(st.lv[3])} · ${price(st.lv[4])}`])
    rows.push(['Buy stops above', st.up.map(price).join(' · ') || '—'], ['Sell stops below', st.dn.map(price).join(' · ') || '—'])
    return (
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-[12px]">
        {rows.map(([k, v]) => (
          <div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="text-right tabular-nums text-strong">{v}</dd></div>
        ))}
      </dl>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <section className={card} aria-label="Day summary">
        <div className="flex flex-wrap items-center gap-2">
          <b className="text-[15px] text-strong">{niceDate(d.date)}</b>
          <span className={`rounded px-1.5 text-[11px] font-bold ${live ? 'bg-up-bg text-up' : 'bg-panel2 text-muted'}`}>{live ? 'LIVE' : 'SIMULATED'}</span>
          <span className="flex-1" />
          <b className="text-[18px]"><MoneyText v={d.pnl} /></b>
        </div>
        <p className="my-1 text-[12px] text-muted">{d.steps} analyses · {d.nows} &quot;NOW&quot; call(s) · {d.trades.length} demo trade(s)</p>
        <button type="button" className={btn} onClick={() => setWhole(true)}>▶ Replay the whole day</button>
      </section>

      <section className={card} aria-label="Chief's calls">
        <h3 className={sect}>Chief&apos;s calls through the day (when the answer changed)</h3>
        {d.timeline.length ? d.timeline.map((a, i) => (
          <div key={i} className="grid grid-cols-[auto_auto_minmax(0,1fr)] items-center gap-2 py-0.5 text-[12px]">
            <span className="tabular-nums text-muted">{hm(a.t)}</span>
            <b className={tone(a)}>{a.a}</b>
            <span className="tabular-nums text-muted">{price(a.p)}{a.cf ? ` · conf ${a.cf}%` : ''}</span>
          </div>
        )) : <p className="text-[12px] text-muted">No analysis saved for this day.</p>}
      </section>

      <section className={card} aria-label="Demo trades">
        <h3 className={sect}>Demo trades · click to replay</h3>
        {d.trades.length ? d.trades.map((t, i) => (
          <button key={i} type="button" onClick={() => setReplay(i)} title="Click to replay"
            className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 border-b border-line py-1.5 text-left text-[12px] last:border-0 hover:bg-hover">
            <span className="tabular-nums text-muted">{tmIn(t.entry_t)}</span>
            <span className="min-w-0 truncate">
              <b className={t.side === 'BUY' ? 'text-up' : 'text-down'}>{t.side}</b>{' '}
              <span className="tabular-nums">{price(t.entry)} → {t.exit != null ? price(t.exit) : 'open'}</span>{' '}
              <span className="text-muted">{t.why || ''}</span>
            </span>
            <b><MoneyText v={t.usd} /></b>
          </button>
        )) : <p className="text-[12px] text-muted">No demo trades this day.</p>}
      </section>

      <section className={card} aria-label="Agents that day">
        <h3 className={sect}>Agents that day · right 4 hours later?</h3>
        {agents.length ? (
          <>
            {agents.map(([k, a]) => {
              const dec = a.hit + a.miss, hr = dec ? Math.round((100 * a.hit) / dec) : null
              return (
                <div key={k} className="grid grid-cols-[minmax(80px,1fr)_2rem_minmax(40px,30%)_2.5rem_auto] items-center gap-2 py-0.5 text-[12px]">
                  <b className="truncate text-strong">{LABELS[k] || k}</b>
                  <span className="text-right tabular-nums text-muted">{a.calls}</span>
                  <div className="h-1.5 rounded bg-panel2"><div className={`h-full rounded ${(hr ?? 0) >= 50 ? 'bg-up' : 'bg-down'}`} style={{ width: `${hr ?? 0}%` }} /></div>
                  <span className="text-right tabular-nums">{hr != null ? `${hr}%` : '—'}</span>
                  <span className="whitespace-nowrap tabular-nums text-muted">{a.hit}✓ {a.miss}✗{a.pending ? ` · ${a.pending} waiting` : ''}</span>
                </div>
              )
            })}
            <p className="mt-1.5 text-[11px] text-muted">Calls repeat every 15 minutes, so neighbouring calls overlap. About 50% is a coin flip.</p>
          </>
        ) : <p className="text-[12px] text-muted">No agent calls saved for this day.</p>}
      </section>

      <section className={card} aria-label="Levels at the start of the day"><h3 className={sect}>Levels at the start of the day</h3>{levels(d.levels.start)}</section>
      <section className={card} aria-label="Levels at the end of the day"><h3 className={sect}>Levels at the end of the day</h3>{levels(d.levels.end)}</section>

      {replay != null && d.trades[replay] && (
        <TradeReplay trade={d.trades[replay]} lot={0.1} onClose={() => setReplay(null)} />
      )}
      {whole && <DayReplay d={d} onClose={() => setWhole(false)} />}
    </div>
  )
}
