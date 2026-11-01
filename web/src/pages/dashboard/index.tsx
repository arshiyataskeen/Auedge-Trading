import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDemo, useJournalAccounts } from '../../api/endpoints'
import { useLivePrice } from '../../api/live'
import PageHeader from '../../components/PageHeader'
import QueryCard from '../../components/QueryCard'
import { money, toneOf } from '../../lib/format'
import { withLivePrice } from '../demo/logic'
import { AccountCard, DemoCard, TONE } from './Cards'
import TodayStrip from './TodayStrip'

const btn = 'rounded border border-line bg-panel2 px-3 py-1.5 text-[12.5px] text-strong no-underline hover:bg-hover'
const btnPrimary = 'rounded border border-accent bg-accent px-3 py-1.5 text-[12.5px] font-semibold text-white no-underline hover:opacity-90'

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

  return (
    <div>
      <PageHeader title="My accounts" subtitle="Prop-firm challenges and funded accounts · phase-wise trading journal"
        actions={<>
          <Link to="/journal" className={btn}>All records</Link>
          <Link to="/journal?new=1" className={btnPrimary}>＋ New account</Link>
        </>} />
      <QueryCard query={accounts} title="Accounts">
        {({ accounts: list }) => {
          const all = list ?? []
          const real = all.filter((a) => a.current && a.id !== demoId)
          const act = real.filter((a) => !a.archived)
          const funded = act.filter((a) => a.current!.is_funded && !a.current!.result).length
          const today = Math.round(act.reduce((s, a) => s + a.current!.check.today_pnl, 0) * 100) / 100
          return (
            <>
              <div className="mb-3 grid grid-cols-2 gap-2 min-[700px]:grid-cols-4">
                <Stat v={act.length} k="active accounts" />
                <Stat v={funded} k="funded" />
                <Stat v={money(today)} k="today, all accounts" tone={toneOf(today)} />
                <Stat v={act.reduce((s, a) => s + (a.n_trades ?? 0), 0)} k="trades logged" />
              </div>
              <TodayStrip demo={demo} accounts={all.filter((a) => a.id !== demoId)} />
              <div className="grid grid-cols-1 gap-3 min-[900px]:grid-cols-[minmax(0,1fr)_minmax(340px,28%)]">
                <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] content-start border-l border-t border-line">
                  <DemoCard dm={demo} to={demoId ? `/journal/${demoId}` : '/demo'} />
                  {real.length ? real.map((a) => <AccountCard key={a.id} a={a} />) : (
                    <Link to="/journal?new=1" className="block border-b border-r border-line bg-panel p-3 text-inherit no-underline hover:bg-panel2">
                      <b className="text-strong">＋ Add your prop-firm account</b>
                      <div className="mt-1 text-[11.5px] text-muted">
                        Enter your firm's rules: profit target, daily loss, max loss and minimum days for each phase. AuEdge tracks them for every trade you log.
                      </div>
                    </Link>
                  )}
                </div>
                <aside className="flex min-w-0 flex-col items-start gap-2">
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
            </>
          )
        }}
      </QueryCard>
    </div>
  )
}
