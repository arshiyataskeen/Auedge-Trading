import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useBacktestResult } from '../../api/endpoints'
import type { BtResult, BtSummary } from '../../api/types'
import BarCell from '../../components/BarCell'
import DayTrades from '../../components/DayTrades'
import EmptyState from '../../components/EmptyState'
import EquityChart from '../../components/EquityChart'
import MoneyText from '../../components/MoneyText'
import MonthCalendar from '../../components/MonthCalendar'
import MonthTable from '../../components/MonthTable'
import QueryCard from '../../components/QueryCard'
import Tabs from '../../components/Tabs'
import TradeReplay from '../../components/TradeReplay'
import { money, price, rtext } from '../../lib/format'
import { groupTrades, sortedKeys } from '../../lib/periods'
import { monthName } from '../../lib/time'
import { card, dlong, dshort, LABELS, sect } from './ui'

const TABS = [
  { key: 'months', label: 'Months' }, { key: 'calendar', label: 'Calendar' },
  { key: 'trades', label: 'Trades' }, { key: 'details', label: 'Details' },
]
const dayLong = (k: string) => new Date(`${k}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
const when = (ts: number) => new Date(ts * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })

/** Loads one saved run and shows it. Re-keyed per run so the view always opens on that run's newest month. */
export default function ResultView({ id }: { id: string }) {
  const q = useBacktestResult(id)
  return (
    <QueryCard query={q} title="Backtest result">
      {(d) => (d as BtResult & { error?: string }).error
        ? <div className={card}><div role="alert" className="text-[12.5px] text-warn">{(d as { error?: string }).error}</div></div>
        : <Loaded key={id} d={d} />}
    </QueryCard>
  )
}

function Stat({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="rounded border border-line p-2">
      <div className="text-[15px] font-semibold tabular-nums text-strong">{children}</div>
      <div className="text-[11px] text-muted">{k}</div>
    </div>
  )
}

function Loaded({ d }: { d: BtResult }) {
  const groups = useMemo(() => groupTrades(d.trades), [d.trades])
  const months = sortedKeys(groups.months)
  const lastMonth = months[months.length - 1] ?? ''
  const [pv, setPv] = useState({ year: lastMonth.slice(0, 4), month: lastMonth, day: null as string | null, open: false })
  const [sub, setSub] = useState('months')
  const [limit, setLimit] = useState(100)
  const [replay, setReplay] = useState<number | null>(null)
  const calRef = useRef<HTMLDivElement>(null)
  const scrollCal = useRef(false)
  useEffect(() => {
    if (scrollCal.current) { scrollCal.current = false; calRef.current?.scrollIntoView?.({ block: 'start', behavior: 'smooth' }) }
  })

  const p = d.params, u = d.usd, hasUsd = groups.hasUsd
  const r = !hasUsd
  const show = (v: number) => (hasUsd ? money(v) : rtext(v))

  if (!d.trades.length) return <div className={card}><EmptyState>No trades in this run.</EmptyState></div>

  const years = sortedKeys(groups.years)
  const pickMonth = (k: string) => {
    scrollCal.current = !(pv.open && pv.month === k)
    setPv({ year: k.slice(0, 4), month: k, day: null, open: !(pv.open && pv.month === k) }); setSub('months')
  }
  const pickYear = (y: string) => {
    const last = months.filter((k) => k.startsWith(y)).pop() ?? ''
    setPv({ year: y, month: last, day: null, open: false }); setSub('months')
  }
  const moveMonth = (dir: -1 | 1) => {
    const k = months[Math.min(months.length - 1, Math.max(0, months.indexOf(pv.month) + dir))]
    if (sub === 'months') scrollCal.current = true
    setPv({ year: k.slice(0, 4), month: k, day: null, open: pv.open })
  }
  const pickDay = (k: string) => {
    setPv({ year: k.slice(0, 4), month: k.slice(0, 7), day: pv.day === k ? null : k, open: sub === 'calendar' ? pv.open : true })
    if (sub !== 'calendar') setSub('months')
  }

  const dayAgg = pv.day ? groups.days.get(pv.day) : null
  const calendar = (
    <section className={card} aria-label="Calendar">
      <h2 className={sect}>Calendar · tap a day to see its trades</h2>
      <MonthCalendar groups={groups} month={pv.month} selectedDay={pv.day} onPickDay={pickDay} onMove={moveMonth} />
      {dayAgg && pv.day ? (
        <div className="mt-3">
          <div className={sect}>{dayLong(pv.day)} · <MoneyText v={dayAgg.pnl} r={r} /></div>
          <DayTrades trades={d.trades} idx={dayAgg.idx} onReplay={setReplay} />
        </div>
      ) : <p className="mt-2 text-[11.5px] text-muted">Tap a day to see its trades.</p>}
    </section>
  )

  const vals = d.trades.map((t) => t.usd ?? t.r)
  const wins = vals.filter((v) => v > 0), losses = vals.filter((v) => v < 0)
  const sum = (a: number[]) => a.reduce((x, y) => x + y, 0)
  const gain = sum(wins), loss = sum(losses)
  let cum = 0
  const curve: [number, number][] = d.trades.map((t) => [t.exit_t, (cum += t.usd ?? t.r)])
  const dayKeys = sortedKeys(groups.days).filter((k) => k.startsWith(pv.month)).reverse()
  const maxDay = Math.max(1, ...dayKeys.map((k) => Math.abs(groups.days.get(k)!.pnl)))
  const best = Math.max(...vals), worst = Math.min(...vals)

  const newest = d.trades.map((_, i) => i).reverse()

  const months$ = (
    <>
      <section className={card} aria-label="Month by month">
        <h2 className={sect}>Month by month · tap a month to see its days</h2>
        <MonthTable groups={groups} year={pv.year} selectedMonth={pv.open ? pv.month : null} onPick={pickMonth} onPickYear={pickYear} />
      </section>
      {pv.open && <div ref={calRef} className="mt-3">{calendar}</div>}
    </>
  )

  const tradesTab = (
    <section className={card} aria-label="Trades">
      <h2 className={sect}>Trades · newest first · click one to replay it</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-[12.5px] tabular-nums">
          <thead>
            <tr className="text-left text-[11px] text-muted">
              <th className="py-1 font-normal">Closed</th><th className="font-normal">Side</th><th className="font-normal">Entry → exit</th>
              <th className="font-normal">Why it closed</th><th className="font-normal">R</th><th className="text-right font-normal">Profit / loss</th>
            </tr>
          </thead>
          <tbody>
            {newest.slice(0, limit).map((i) => {
              const t = d.trades[i]
              return (
                <tr key={i} data-ti={i} title="Click to replay" onClick={() => setReplay(i)} className="cursor-pointer border-t border-line hover:bg-hover">
                  <td className="py-1.5">{when(t.exit_t)}</td>
                  <td className={`font-bold ${t.side === 'BUY' ? 'text-up' : 'text-down'}`}>{t.side}</td>
                  <td>{price(t.entry)} → {price(t.exit)}</td>
                  <td className="text-muted">{t.why}</td>
                  <td><MoneyText v={t.r} r /></td>
                  <td className="text-right"><MoneyText v={hasUsd ? t.usd : t.r} r={r} /></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {newest.length > limit && (
        <button type="button" onClick={() => setLimit(limit + 100)}
          className="mt-2 rounded border border-line bg-panel2 px-3 py-1.5 text-[12.5px] text-strong hover:bg-hover">
          Show {Math.min(100, newest.length - limit)} more ({newest.length - limit} left)
        </button>
      )}
    </section>
  )

  return (
    <div className="grid grid-cols-1 gap-3 min-[900px]:grid-cols-[minmax(0,1fr)_minmax(340px,28%)]">
      <div className="min-w-0 space-y-3">
        <section className={card} aria-label="Result">
          <h2 className={sect}>Result · {dlong(p.start)} – {dlong(p.end - 86400)}</h2>
          <p className="mb-2 text-[11.5px] text-muted">
            {p.lot} lot · ${(+(u ? u.account : p.account || 0)).toLocaleString()} account · day limits −${p.day_max_loss || 'off'} / +${p.day_max_profit || 'off'}
            {p.source ? ` · ${p.source}` : ''}
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {u ? (
              <>
                <Big k="Ending balance"><span>{`$${Math.round(u.end_balance).toLocaleString()}`}</span></Big>
                <Big k="Profit / loss"><MoneyText v={u.total_usd} /></Big>
                <Big k="Return"><span className={u.return_pct > 0 ? 'text-up' : u.return_pct < 0 ? 'text-down' : ''}>{u.return_pct > 0 ? '+' : ''}{u.return_pct}%</span></Big>
              </>
            ) : <Big k="Result"><MoneyText v={d.summary.total_r} r /></Big>}
            <Big k="Trading days"><span>{groups.days.size}</span></Big>
          </div>
          {u && (
            <p className="mt-2 text-[11.5px] text-muted">
              Biggest drop from a high: <b className="text-down">${Math.round(u.max_dd_usd).toLocaleString()}</b> · at worst {d.summary.streak} losses in a row.
            </p>
          )}
        </section>

        <Tabs items={TABS} value={sub} onChange={setSub} label="Result views">
          <div className="pt-3">{months$}</div>
          <div className="pt-3">{calendar}</div>
          <div className="pt-3">{tradesTab}</div>
          <div className="pt-3"><Details d={d} /></div>
        </Tabs>
      </div>

      <aside className="min-w-0 space-y-3">
        <section className={card} aria-label="Stats">
          <h2 className={sect}>Stats · this run</h2>
          <div className="mb-3 grid grid-cols-2 gap-2">
            <Stat k="closed trades">{vals.length}</Stat>
            <Stat k="win rate">{Math.round((100 * wins.length) / vals.length)}%</Stat>
            <Stat k="average win">{wins.length ? <span className="text-up">{show(gain / wins.length)}</span> : '—'}</Stat>
            <Stat k="average loss">{losses.length ? <span className="text-down">{show(loss / losses.length)}</span> : '—'}</Stat>
            <Stat k="profit factor">{loss ? (gain / -loss).toFixed(2) : '—'}</Stat>
            <Stat k="average R"><MoneyText v={d.summary.avg_r} r /></Stat>
            <Stat k="best"><MoneyText v={best} r={r} /></Stat>
            <Stat k="worst"><MoneyText v={worst} r={r} /></Stat>
          </div>
          <EquityChart curve={curve} unit={hasUsd ? '$' : 'R'} />
        </section>

        {dayKeys.length > 0 && (
          <section className={card} aria-label="Day by day">
            <h2 className={sect}>Day by day · {monthName(pv.month)}</h2>
            {dayKeys.map((k) => {
              const x = groups.days.get(k)!
              return (
                <button key={k} type="button" data-day={k} onClick={() => pickDay(k)} aria-pressed={k === pv.day}
                  className={`grid w-full grid-cols-[5.5rem_minmax(0,1fr)_auto] items-center gap-2 rounded px-1 py-1 text-left text-[12px] hover:bg-hover ${k === pv.day ? 'bg-hover' : ''}`}>
                  <span className="tabular-nums">{k}</span>
                  <BarCell value={x.pnl} max={maxDay} label={`${k} result`} />
                  <b><MoneyText v={x.pnl} r={r} /></b>
                </button>
              )
            })}
          </section>
        )}

        {years.length > 1 && (
          <section className={card} aria-label="By year">
            <h2 className={sect}>By year</h2>
            <table className="w-full text-[12.5px] tabular-nums">
              <tbody>
                {years.map((y) => {
                  const x = groups.years.get(y)!
                  return (
                    <tr key={y} onClick={() => pickYear(y)} className="cursor-pointer border-t border-line first:border-t-0 hover:bg-hover">
                      <td className="py-1.5 font-bold text-strong">{y}</td><td>{x.n}</td><td>{Math.round((100 * x.won) / x.n)}%</td>
                      <td className="text-right"><MoneyText v={x.pnl} r={r} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>
        )}
      </aside>

      {replay != null && d.trades[replay] && (
        <TradeReplay trade={d.trades[replay]} src={p.source ? 'backup' : undefined} lot={p.lot} onClose={() => setReplay(null)} />
      )}
    </div>
  )
}

function Big({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-[11px] text-muted">{k}</div>
      <div className="text-[20px] font-semibold tabular-nums text-strong">{children}</div>
    </div>
  )
}

const BLOCKED: [string, string][] = [
  ['day_profit_target', 'daily profit target reached'], ['day_loss_limit', 'daily loss limit reached'],
  ['day_loss_room', "stop too wide for the day's loss limit"], ['daily_cap', '2 trades already that day'],
  ['news', 'news window'], ['friday', 'Friday afternoon'], ['two_losses', '2 losses already that day'],
  ['cooldown', 'cool-down after a loss'], ['chase', 'chasing a big move'], ['f_session', 'outside London / NY hours'],
  ['f_trend', 'Daily and 4H not both agreeing'], ['f_hunt', 'no stop hunt first'],
]

function Details({ d }: { d: BtResult }) {
  const p = d.params, s = d.summary, u = d.usd
  const c = d.counts as Record<string, unknown>
  const skipped = BLOCKED.filter(([n]) => Number(c['blocked_' + n]) > 0).map(([n, t]) => `${c['blocked_' + n]} × ${t}`)
  const rules = [
    `${dshort(p.start)} – ${dshort(p.end - 86400)}`, `${p.step} steps`, `$${(+p.spread).toFixed(2)} per side`,
    p.target_rr ? `target ${p.target_rr}R` : "plan's target", p.partial === false ? '' : 'half off at 1R',
    p.adaptive ? 'performance weights' : 'fixed weights',
    p.day_max_loss || p.day_max_profit ? `day limits −$${p.day_max_loss || 'off'} / +$${p.day_max_profit || 'off'}` : '',
    p.live_rules === false ? 'without live rules' : p.live_rules ? 'live rules' : '',
    p.stop_slip ? `+$${p.stop_slip} stop slippage` : '', p.f_session ? 'London/NY hours only' : '',
    p.f_trend ? 'Daily+4H agree only' : '', p.f_hunt ? 'after stop hunt only' : '',
  ].filter(Boolean)
  const groupsRows = Object.entries(d.groups).filter(([, g]) => (g as BtSummary).n)
  const agents = Object.entries(d.agents)
    .sort((a, b) => ((b[1].hit_rate as number) ?? 0) - ((a[1].hit_rate as number) ?? 0))
  const wh = ((c.weights_history as { mult: Record<string, number> }[] | undefined) ?? []).filter((w) => Object.keys(w.mult).length)
  const lastW = wh[wh.length - 1]
  const cell = 'py-1.5'
  return (
    <div className="space-y-3">
      <section className={card} aria-label="Rules used">
        <h2 className={sect}>Rules used</h2>
        <p className="text-[12.5px] text-text">{rules.join(' · ')}</p>
        {skipped.length > 0 && <p className="mt-2 text-[11.5px] text-muted">Trades skipped by the rules: {skipped.join(' · ')}.</p>}
      </section>

      <section className={card} aria-label="Result in R">
        <h2 className={sect}>Result in R</h2>
        {u && (
          <p className="mb-2 text-[11.5px] text-muted">
            Average trade <MoneyText v={u.avg_usd} /> · best <MoneyText v={u.best_usd} /> · worst <MoneyText v={u.worst_usd} /> · worst drop ${Math.round(u.max_dd_usd).toLocaleString()}.
            Average risk per trade ${Math.round(u.avg_risk_usd || 0).toLocaleString()} at {p.lot} lot (stop distance × {Math.round(p.lot * 100)} oz).
          </p>
        )}
        <div className="mb-3 grid grid-cols-3 gap-2 sm:grid-cols-6">
          <Stat k="trades">{s.n}</Stat><Stat k="win rate">{s.win_rate != null ? `${s.win_rate}%` : '—'}</Stat>
          <Stat k="average"><MoneyText v={s.avg_r} r /></Stat><Stat k="total"><MoneyText v={s.total_r} r /></Stat>
          <Stat k="worst drop">{s.max_dd.toFixed(1)}R</Stat><Stat k="losses in a row">{s.streak}</Stat>
        </div>
        <EquityChart curve={d.equity} />
        <ul className="mt-2 list-disc space-y-1 pl-5 text-[12px] text-text">{d.lines.map((x, i) => <li key={i}>{x.trim()}</li>)}</ul>
        <p className="mt-2 text-[11.5px] text-muted">R = result in &quot;risk units&quot;: 1R is what you lose when the stop is hit. Past results do not guarantee future results.</p>
      </section>

      {lastW && (
        <section className={card} aria-label="Performance weights">
          <h2 className={sect}>Performance weights in the last week of the test ({wh.length} weeks adjusted)</h2>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(lastW.mult).sort((a, b) => b[1] - a[1]).map(([k, m]) => (
              <span key={k} className={`rounded border border-line px-2 py-0.5 text-[12px] ${m > 1 ? 'text-up' : 'text-down'}`}>{LABELS[k] || k} ×{m.toFixed(2)}</span>
            ))}
          </div>
        </section>
      )}

      {groupsRows.length > 0 && (
        <section className={card} aria-label="Split">
          <h2 className={sect}>Split</h2>
          <table className="w-full text-[12.5px] tabular-nums"><tbody>
            {groupsRows.map(([k, g]) => (
              <tr key={k} className="border-t border-line first:border-t-0">
                <td className={cell}>{k}</td><td>{g.n}</td><td>{g.win_rate}%</td>
                <td className="text-right"><MoneyText v={g.total_r} r /></td>
              </tr>
            ))}
          </tbody></table>
        </section>
      )}

      <section className={card} aria-label="Agents">
        <h2 className={sect}>Agents: 4-hour direction right?</h2>
        <table className="w-full text-[12.5px] tabular-nums"><tbody>
          {agents.map(([k, a]) => {
            const hr = a.hit_rate as number | null
            return (
              <tr key={k} className="border-t border-line first:border-t-0">
                <td className={`${cell} font-bold text-strong`}>{LABELS[k] || (k === 'chief' ? 'Chief direction' : k)}</td>
                <td className="w-[38%]">
                  <div className="h-2 rounded bg-panel2"><div className={`h-full rounded ${(hr ?? 0) >= 50 ? 'bg-up' : 'bg-down'}`} style={{ width: `${hr ?? 0}%` }} /></div>
                </td>
                <td>{hr != null ? `${hr}%` : '—'}</td>
                <td className="text-right text-muted">{String(a.hits)}/{Number(a.hits) + Number(a.misses)}</td>
              </tr>
            )
          })}
        </tbody></table>
        <p className="mt-1.5 text-[11.5px] text-muted">About 50% is a coin flip.</p>
      </section>
    </div>
  )
}
