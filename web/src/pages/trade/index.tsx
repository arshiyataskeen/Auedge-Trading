import { useEffect, useState } from 'react'
import { useAnalysis, useRefreshAnalysis } from '../../api/endpoints'
import type { Analysis } from '../../api/types'
import PageHeader from '../../components/PageHeader'
import QueryCard from '../../components/QueryCard'
import Tabs from '../../components/Tabs'
import ChartArea from './ChartArea'
import ChiefDetails from './ChiefDetails'
import Decision from './Decision'
import LevelsPanel from './LevelsPanel'
import { levelRows, useStored } from './logic'
import PlanPanel from './PlanPanel'

const ICON = 'h-[17px] w-[17px] fill-none stroke-current'
const BTN = 'grid h-8 w-8 place-items-center rounded border text-muted hover:bg-hover disabled:opacity-50'

/** Old aStatus line: when the analysis ran, the data check, Claude summary and adapter problems. */
function Status({ d }: { d: Analysis }) {
  const dc = d.data_check
  return (
    <div className="border-t border-line px-3 py-2 text-[11.5px] text-muted">
      Updated {new Date(d.generated_at).toLocaleTimeString()} · data: <b className={dc.veto ? 'text-warn' : ''}>{dc.headline}</b>
      {d.ai_enabled ? ' · Claude summary on' : ''}
      {d.adapter_problems.length ? ` · adapter problems: ${d.adapter_problems.join('; ')}` : ''}
      {' · click the decision for details'}
    </div>
  )
}

/** Old tickNext: "m:ss" until the server's next 15-minute step is due. */
function useNextIn(updatedAt: number, nextInS: number | undefined) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id) }, [])
  if (nextInS == null) return '--:--'
  const left = Math.max(0, Math.round((updatedAt + (nextInS + 2) * 1000 - now) / 1000))
  return `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`
}

/** /trade: the chart (TradingView, Spot + zones, Futures) next to the Chief analyst's plan and levels. */
export default function TradePage() {
  const analysis = useAnalysis()
  const refresh = useRefreshAnalysis()
  const d = analysis.data
  const nextIn = useNextIn(analysis.dataUpdatedAt, d?.next_in_s)
  const [wide, setWide] = useState(false)
  const [details, setDetails] = useState(false)
  const [tab, setTab] = useStored('trade.tab', 'plan')
  const [lv, setLv] = useStored('lvMode', 'day')
  const mode = lv === 'all' ? 'all' : 'day'
  const lvCount = d ? levelRows(d.chief, d.agents, d.chief.price, mode).rows.length : 0
  const items = [{ key: 'plan', label: 'Plan' }, { key: 'levels', label: lvCount ? `Levels ${lvCount}` : 'Levels' }]

  const actions = (
    <>
      <span className="rounded border border-line px-2 py-1 text-[11.5px] text-muted" title="All agents re-run 20 seconds after every 15-minute candle closes">
        Next analysis <b className="tabular-nums text-strong">{nextIn}</b>
      </span>
      <button type="button" aria-label="Refresh the analysis" title="Run all agents again now" disabled={refresh.isPending}
        onClick={() => refresh.mutate()} className={`${BTN} border-accent bg-accent text-white`}>
        <svg viewBox="0 0 24 24" className={`${ICON} ${refresh.isPending ? 'animate-spin' : ''}`} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M19.5 10.5A7.8 7.8 0 0 0 5 8.2" /><path d="M4.6 4v4.4H9" /><path d="M4.5 13.5A7.8 7.8 0 0 0 19 15.8" /><path d="M19.4 20v-4.4H15" />
        </svg>
      </button>
      <button type="button" aria-label="Bigger chart" aria-pressed={wide} onClick={() => setWide((v) => !v)}
        title={wide ? 'Show the analysis panel again' : 'Bigger chart: hide the analysis panel'}
        className={`${BTN} max-[899px]:hidden ${wide ? 'border-accent bg-acc-bg text-strong' : 'border-line'}`}>
        <svg viewBox="0 0 24 24" className={ICON} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>
      </button>
    </>
  )

  return (
    <div>
      <PageHeader title="Trade" actions={actions}
        subtitle={refresh.isPending ? 'Running all agents…' : refresh.isError ? <span className="text-down">Refresh failed: {(refresh.error as Error).message}</span> : 'Chart and the Chief analyst plan'} />
      <div className={`grid grid-cols-1 gap-3 ${wide ? '' : 'min-[900px]:grid-cols-[minmax(0,1fr)_minmax(340px,28%)]'}`}>
        <ChartArea analysis={d} />
        <section data-testid="trade-panel" aria-label="Analysis panel"
          className={`flex min-w-0 flex-col self-start rounded border border-line bg-panel min-[900px]:max-h-[calc(100svh-9rem)] min-[900px]:overflow-y-auto ${wide ? 'min-[900px]:hidden' : ''}`}>
          <QueryCard query={analysis} title="Plan">
            {(a) => (
              <>
                <Decision d={a} onOpen={() => setDetails(true)} />
                <div className="px-2 pb-2 pt-1">
                  <Tabs items={items} value={tab === 'levels' ? 'levels' : 'plan'} onChange={setTab} label="Analysis panels">
                    <PlanPanel d={a} />
                    <LevelsPanel d={a} mode={mode} onMode={setLv} />
                  </Tabs>
                </div>
                <Status d={a} />
                {details && <ChiefDetails d={a} onClose={() => setDetails(false)} />}
              </>
            )}
          </QueryCard>
        </section>
      </div>
    </div>
  )
}
