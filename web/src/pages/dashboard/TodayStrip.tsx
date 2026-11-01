import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useAnalysis, useNews } from '../../api/endpoints'
import type { Demo, JournalAccount } from '../../api/types'
import { price } from '../../lib/format'
import { Bias, Signed, usd } from './Cards'

import { btn, btnPrimary } from './ui'

function Cell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col items-start gap-1.5 border-b border-r border-line bg-panel p-3">
      <div className="text-[10px] uppercase tracking-wide text-muted">{title}</div>
      {children}
    </div>
  )
}
const Meta = ({ children, cls = '' }: { children: ReactNode; cls?: string }) => <div className={`text-[11.5px] text-muted ${cls}`}>{children}</div>

/** Old nextIn: m:ss until the next analysis. */
function nextIn(at: number | null, now: number): string {
  if (!at) return '—'
  const s = Math.max(0, Math.round((at - now) / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** Port of todayHtml: AuEdge's call, the demo position, today's result, next big news. `demo` carries live-price P&L. */
export default function TodayStrip({ demo, accounts }: { demo: Demo | undefined; accounts: JournalAccount[] | undefined }) {
  const analysis = useAnalysis()
  const news = useNews()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id) }, [])

  const a = analysis.data, c = a?.chief, plan = c?.plan
  const nextAt = a ? analysis.dataUpdatedAt + a.next_in_s * 1000 : null

  const call = !c || !plan ? <Meta>Loading the analysis…</Meta> : (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Bias kind={plan.kind === 'now' ? (plan.side ?? 'NA') : plan.kind === 'watch' ? 'NA' : 'WAIT'}>{plan.action}</Bias>
        <Meta>confidence {c.confidence}% · next in <b className="tabular-nums">{nextIn(nextAt, now)}</b></Meta>
      </div>
      {plan.kind === 'now' ? (
        <>
          <Meta>Entry {price(((plan.entry_lo ?? 0) + (plan.entry_hi ?? 0)) / 2)} · stop {price(plan.stop)} · half {price(plan.be_at)} · target {price(plan.t1)}</Meta>
          <Link to="/journal?call=1" className={`inline-block ${btnPrimary}`}>＋ Add to my journal</Link>
        </>
      ) : <Meta cls="line-clamp-2">{c.headline || ''}</Meta>}
      <Link to="/trade" className={`inline-block ${btn}`}>Chart dashboard →</Link>
    </>
  )

  const dpos = demo?.open ?? []
  const dflo = dpos.reduce((s, t) => s + (t.unrealised || 0), 0)
  const demoCell = !demo ? <Meta>Loading the demo account…</Meta> : dpos.length ? (
    <>
      <div className="flex w-full items-center gap-2">
        <Bias kind={dpos[0].side}>{dpos[0].side}</Bias><b className="text-strong">{dpos[0].lot} lot</b>
        <b className="ml-auto text-[15px]"><Signed v={Math.round(dflo * 100) / 100} /></b>
      </div>
      <Meta>Entry {price(dpos[0].entry)} · stop {price(dpos[0].stop_now ?? dpos[0].stop)}{dpos[0].half ? ' (breakeven)' : ''} · half {price(dpos[0].be)} · target {price(dpos[0].t1)}</Meta>
      <Link to="/demo" className={`inline-block ${btn}`}>Open the Demo tab →</Link>
    </>
  ) : (
    <>
      <div className="text-[15px] font-bold text-strong">No open trade</div>
      <Meta>Balance {usd(demo.balance)} · {demo.trades} closed trade(s) · waiting for the next BUY / SELL NOW call.</Meta>
      <Link to="/demo" className={`inline-block ${btn}`}>Open the Demo tab →</Link>
    </>
  )

  // Intentional: the demo journal account is excluded (the old page double-counted it with the demo's own P&L).
  const jToday = (accounts ?? []).filter((x) => !x.archived && x.current).reduce((s, x) => s + x.current!.check.today_pnl, 0)
  const nowS = now / 1000
  const ev = (news.data?.events ?? []).find((e) => e.t > nowS && e.impact === 'High')
  const evIn = ev ? ev.t - nowS : 0

  return (
    <div className="mb-3 grid grid-cols-1 min-[640px]:grid-cols-2 min-[1100px]:grid-cols-[1.3fr_1.3fr_0.9fr_1fr] border-l border-t border-line" data-testid="today-strip">
      <Cell title="AuEdge call">{call}</Cell>
      <Cell title="AuEdge demo position">{demoCell}</Cell>
      <Cell title="Today">
        {demo && (
          <>
            <div className="text-[18px] font-bold"><Signed v={demo.today} /></div>
            <Meta>AuEdge demo · this week <Signed v={demo.week} /></Meta>
          </>
        )}
        <Meta cls="mt-1">Journal accounts <b><Signed v={Math.round(jToday * 100) / 100} /></b></Meta>
      </Cell>
      <Cell title="Next big news">
        {ev ? (
          <>
            <b className="text-strong">{ev.name}</b>
            <Meta>
              {new Date(ev.t * 1000).toLocaleString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' })} ·{' '}
              in {evIn > 86400 ? `${Math.round(evIn / 86400)} day(s)` : `${Math.floor(evIn / 3600)}h ${Math.floor((evIn % 3600) / 60)}m`}
              {ev.blocks ? ' · no new trades around it' : ''}
            </Meta>
          </>
        ) : <Meta>No high-impact US news coming up.</Meta>}
      </Cell>
    </div>
  )
}
