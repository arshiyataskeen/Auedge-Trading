import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useJournalAccounts, useJournalTrades } from '../../api/endpoints'
import type { JournalTrade } from '../../api/types'
import PageHeader from '../../components/PageHeader'
import QueryCard from '../../components/QueryCard'
import { money, toneOf } from '../../lib/format'
import { TONE } from '../dashboard/Cards'
import JCalendar from './JCalendar'
import { downloadCsv, recFiltered, type RecFilters } from './logic'
import { btnCls, btnPrimaryCls, Card, Field as F, inputCls, linkBtn, Meta, segCls, Stat, TradeTable } from './ui'

/** Port of openRecords / renderRecords: every trade of every account, with filters, List / Calendar and a CSV download. */
export default function Records({ onAddTrade, onNewAccount, onOpenTrade }: {
  onAddTrade: () => void; onNewAccount: () => void; onOpenTrade: (t: JournalTrade) => void
}) {
  const q = useJournalTrades()
  const accounts = useJournalAccounts(true)
  const [f, setF] = useState<RecFilters>({})
  const [cal, setCal] = useState(false)
  const set = (k: keyof RecFilters, v: string) => setF((s) => ({ ...s, [k]: v }))
  const all = useMemo(() => q.data?.trades ?? [], [q.data])
  const rows = useMemo(() => recFiltered(all, f), [all, f])

  const closed = rows.filter((t) => t.net != null)
  const tot = closed.reduce((s, t) => s + t.net, 0)
  const wins = closed.filter((t) => t.net > 0), losses = closed.filter((t) => t.net < 0)
  const rs = closed.filter((t) => t.r != null).map((t) => t.r as number)
  const days: Record<string, { pnl: number; n: number }> = {}
  for (const t of closed) { const d = days[t.day] ?? (days[t.day] = { pnl: 0, n: 0 }); d.pnl += t.net; d.n++ }
  const uniq = (k: 'phase' | 'setup') => [...new Set(all.map((t) => t[k]).filter(Boolean) as string[])].sort()
  const net = Math.round(tot * 100) / 100
  const pf = losses.length && wins.length ? (wins.reduce((s, t) => s + t.net, 0) / -losses.reduce((s, t) => s + t.net, 0)).toFixed(2) : '—'

  return (
    <div>
      <div className="mb-1"><Link to="/dashboard" className={linkBtn}>← All accounts</Link></div>
      <PageHeader title="All records" subtitle={`Every trade in every account · ${all.length} in total`}
        actions={<>
          <button type="button" className={btnPrimaryCls} onClick={onAddTrade}>＋ Add trade</button>
          <button type="button" className={btnCls} onClick={onNewAccount}>＋ New account</button>
          <button type="button" className={btnCls} disabled={!rows.length} onClick={() => downloadCsv(rows)}>Download CSV</button>
        </>} />
      <QueryCard query={q} title="Trades">
        {() => (
          <div className="flex flex-col gap-3">
            <Card label="Filters">
              <div className="flex flex-wrap items-end gap-3">
                <F t="Account">
                  <select className={inputCls} value={f.acc ?? ''} onChange={(e) => set('acc', e.target.value)}>
                    <option value="">All</option>
                    {(accounts.data?.accounts ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                </F>
                <F t="Phase">
                  <select className={inputCls} value={f.phase ?? ''} onChange={(e) => set('phase', e.target.value)}>
                    <option value="">All</option>{uniq('phase').map((x) => <option key={x} value={x}>{x}</option>)}
                  </select>
                </F>
                <F t="Side">
                  <select className={inputCls} value={f.side ?? ''} onChange={(e) => set('side', e.target.value)}>
                    <option value="">Both</option><option value="BUY">BUY</option><option value="SELL">SELL</option>
                  </select>
                </F>
                <F t="Result">
                  <select className={inputCls} value={f.res ?? ''} onChange={(e) => set('res', e.target.value)}>
                    <option value="">All</option><option value="win">Wins</option><option value="loss">Losses</option><option value="open">Open</option>
                  </select>
                </F>
                <F t="Setup">
                  <select className={inputCls} value={f.setup ?? ''} onChange={(e) => set('setup', e.target.value)}>
                    <option value="">All</option>{uniq('setup').map((x) => <option key={x} value={x}>{x}</option>)}
                  </select>
                </F>
                <F t="From"><input type="date" className={inputCls} value={f.from ?? ''} onChange={(e) => set('from', e.target.value)} /></F>
                <F t="To"><input type="date" className={inputCls} value={f.to ?? ''} onChange={(e) => set('to', e.target.value)} /></F>
                <F t="Search notes">
                  <input className={`${inputCls} w-[140px]`} value={f.q ?? ''} placeholder="e.g. revenge" onChange={(e) => set('q', e.target.value)} />
                </F>
                {Object.values(f).some(Boolean) && <button type="button" className={linkBtn} onClick={() => setF({})}>Clear filters</button>}
              </div>
            </Card>
            <div className="grid grid-cols-2 gap-2 min-[700px]:grid-cols-4">
              <Stat v={rows.length} k="trades shown" />
              <Stat v={closed.length ? `${Math.round((100 * wins.length) / closed.length)}%` : '—'} k="win rate" />
              <Stat v={<span className={TONE[toneOf(net)]}>{money(net)}</span>} k="net result" />
              <Stat v={pf} k="profit factor" />
            </div>
            <div className="flex gap-1" role="group" aria-label="Records view">
              <button type="button" aria-pressed={!cal} className={segCls(!cal, 'px-3')} onClick={() => setCal(false)}>List</button>
              <button type="button" aria-pressed={cal} className={segCls(cal, 'px-3')} onClick={() => setCal(true)}>Calendar</button>
            </div>
            <Card>
              {cal ? <JCalendar resetKey={JSON.stringify(f)} days={days} trades={rows} showAcc onOpenTrade={onOpenTrade} />
                : rows.length ? (
                  <>
                    <TradeTable trades={rows} showAcc onOpen={onOpenTrade} />
                    {rs.length > 0 && <Meta cls="mt-1.5">Average result {(rs.reduce((a, b) => a + b, 0) / rs.length).toFixed(2)}R over {rs.length} trades with a stop.</Meta>}
                  </>
                ) : <Meta>No trades match.</Meta>}
            </Card>
          </div>
        )}
      </QueryCard>
    </div>
  )
}
