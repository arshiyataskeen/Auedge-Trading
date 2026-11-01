import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDemo, useJournalAccounts } from '../../api/endpoints'
import { useLivePrice } from '../../api/live'
import PageHeader from '../../components/PageHeader'
import QueryCard from '../../components/QueryCard'
import { money, toneOf } from '../../lib/format'
import { withLivePrice } from '../demo/logic'
import LoadingCard from '../../components/LoadingCard'
import { AccountCard, DemoCard, EMPTY, TONE } from './Cards'
import SessionsDial from '../../components/SessionsDial'
import TodayStrip from './TodayStrip'
import { btn, btnPrimary } from './ui'

function Stat({ v, k, tone = '' }: { v: string | number; k: string; tone?: 'up' | 'dn' | '' }) {
  return (
    <div className="rounded border border-line bg-panel p-2">
      <div className={`text-[18px] font-semibold tabular-nums text-strong ${TONE[tone]}`}>{v}</div>
      <div className="text-[11px] text-muted">{k}</div>
    </div>
  )
}

/** Port of the old Home ("My accounts"): totals, today strip, account cards, tips. */
export default function DashboardPage() {
  const [archived, setArchived] = useState(false)
  const accounts = useJournalAccounts(archived)
  const demoQ = useDemo()
  const live = useLivePrice()
  // liveDemoTick: open P&L and equity follow the top-bar price between the 30 s refetches.
  const demo = useMemo(() => {
    const d = demoQ.data
    if (!d) return undefined
    const v = withLivePrice(d.open, d.balance, d.equity, live.price)
    return { ...d, open: v.open, equity: v.equity }
  }, [demoQ.data, live.price])
  const demoId = demoQ.data?.journal_account
  // Hold the totals/cards until /api/demo has settled (success or failure) so the demo account never flashes in.
  const settled = !demoQ.isPending
  const list = accounts.data?.accounts ?? []
  const real = settled ? list.filter((a) => a.current && a.id !== demoId) : []
  const act = real.filter((a) => !a.archived)
  const ready = settled && accounts.data !== undefined
  const today = Math.round(act.reduce((s, a) => s + a.current!.check.today_pnl, 0) * 100) / 100
  const funded = act.filter((a) => a.current!.is_funded && !a.current!.result).length

  return (
    <div>
      <PageHeader title="My accounts" subtitle="Prop-firm challenges and funded accounts · phase-wise trading journal"
        actions={<>
          <Link to="/journal" className={`${btn} px-3 py-1.5`}>All records</Link>
          <Link to="/journal?new=1" className={`${btnPrimary} px-3 py-1.5`}>＋ New account</Link>
        </>} />
      <div className="mb-3 grid grid-cols-2 gap-2 min-[700px]:grid-cols-4">
        <Stat v={ready ? act.length : '—'} k="active accounts" />
        <Stat v={ready ? funded : '—'} k="funded" />
        <Stat v={ready ? money(today) : '—'} k="today, all accounts" tone={ready ? toneOf(today) : ''} />
        <Stat v={ready ? act.reduce((s, a) => s + (a.n_trades ?? 0), 0) : '—'} k="trades logged" />
      </div>
      <TodayStrip demo={demo} accounts={settled ? list.filter((a) => a.id !== demoId) : undefined} />
      <div className="grid grid-cols-1 gap-3 min-[900px]:grid-cols-[minmax(0,1fr)_minmax(340px,28%)]">
        <div className="min-w-0">
          <QueryCard query={accounts} title="Accounts">
            {() => !settled ? <LoadingCard /> : (
              <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] content-start border-l border-t border-line">
                <DemoCard dm={demo} to={demoId ? `/journal/${demoId}` : '/demo'} />
                {real.length ? real.map((a) => <AccountCard key={a.id} a={a} />) : (
                  <Link to="/journal?new=1" className={EMPTY}>
                    <b className="text-strong">＋ Add your prop-firm account</b>
                    <div className="text-[11.5px] text-muted">
                      Enter your firm's rules: profit target, daily loss, max loss and minimum days for each phase. AuEdge tracks them for every trade you log.
                    </div>
                  </Link>
                )}
              </div>
            )}
          </QueryCard>
        </div>
        <aside className="flex min-w-0 flex-col items-start gap-2">
          <SessionsDial />
          <section className="w-full rounded border border-line bg-panel p-3">
            <h2 className="mb-2 text-[12px] font-semibold text-strong">Tips</h2>
            <ul className="list-disc space-y-1.5 pl-4 text-[12px] text-muted">
              <li>Log every trade, wins and losses, with how you felt and whether you followed your plan.</li>
              <li>Check <b className="text-strong">today's loss room</b> before each trade; never risk more than what's left.</li>
              <li>The journal checks closed trades only. Your firm also counts open (floating) losses, so leave a buffer.</li>
            </ul>
          </section>
          <button type="button" onClick={() => setArchived((v) => !v)} className="text-[12px] text-accent underline">
            {archived ? 'Hide archived accounts' : 'Show archived accounts'}
          </button>
        </aside>
      </div>
    </div>
  )
}
