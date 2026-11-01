import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { qk, useBacktestInfo, useBacktestStatus } from '../../api/endpoints'
import EmptyState from '../../components/EmptyState'
import PageHeader from '../../components/PageHeader'
import QueryCard from '../../components/QueryCard'
import { money } from '../../lib/format'
import HealthCheck from './HealthCheck'
import NewRunForm from './NewRunForm'
import ResultView from './ResultView'
import { btn, btnOn, dshort, field, pctOf } from './ui'

type Panel = 'new' | 'health' | null

/** Port of the old Backtest tab: saved-run picker, New backtest / Health check panels, and the opened run. */
export default function BacktestPage() {
  const qc = useQueryClient()
  const info = useBacktestInfo()
  const [polling, setPolling] = useState(false)
  const status = useBacktestStatus(polling)
  const running = !!status.data?.running
  useEffect(() => { setPolling(running) }, [running])

  const [panel, setPanel] = useState<Panel>(null)
  const [picked, setPicked] = useState<string | null>(null)
  const [finishedError, setFinishedError] = useState<string | null>(null)

  // A run or health check just finished: refresh the list and open the new run (old btPoll).
  const wasRunning = useRef(false)
  useEffect(() => {
    const st = status.data
    if (running) { wasRunning.current = true; setFinishedError(null); return }
    if (!wasRunning.current || !st) return
    wasRunning.current = false
    const id = String(st.id ?? '')
    if (st.error) { setFinishedError(st.error); return }
    if (id.startsWith('hc_')) qc.invalidateQueries({ queryKey: qk.health })
    else if (id.startsWith('bt_')) { qc.invalidateQueries({ queryKey: qk.btInfo }); setPicked(id) }
  }, [running, status.data, qc])

  const runs = info.data?.runs ?? []
  const shown = picked ?? runs[0]?.id ?? null
  const usdTxt = (v: number | null) => (v == null ? '' : ` · ${money(v)}`)
  const pct = pctOf(status.data?.progress)

  const toggle = (p: Exclude<Panel, null>) => setPanel((cur) => (cur === p ? null : p))

  return (
    <div>
      <PageHeader
        title="Backtest"
        subtitle="Today's rules replayed on past gold prices. Pick a saved run, or start a new one."
        actions={
          <>
            {running && <span className="text-[12px] text-muted" role="status">Running… {pct}%</span>}
            <select aria-label="Saved runs" className={`${field} max-w-[320px]`} value={shown ?? ''}
              disabled={!runs.length} onChange={(e) => setPicked(e.target.value)}>
              {runs.length ? runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {dshort(r.start)} – {dshort(r.end - 86400)} · {String(r.step)} · {r.n} trades{usdTxt(r.total_usd)}
                </option>
              )) : <option value="">{info.isLoading ? 'Loading…' : 'No saved runs yet'}</option>}
            </select>
            <button type="button" aria-pressed={panel === 'new'} className={panel === 'new' ? btnOn : btn} onClick={() => toggle('new')}>＋ New backtest</button>
            <button type="button" aria-pressed={panel === 'health'} className={panel === 'health' ? btnOn : btn} onClick={() => toggle('health')}>Health check</button>
          </>
        }
      />

      {/* Panels open below the header, only when clicked, so nothing above loaded content ever shifts. */}
      {panel === 'new' && info.data && <NewRunForm info={info.data} status={status.data} running={running} />}
      {panel === 'new' && !info.data && info.isLoading && <div className="mb-3 rounded border border-line bg-bg p-3 text-[12px] text-muted">Loading…</div>}
      {panel === 'health' && <HealthCheck status={status.data} running={running} />}
      {finishedError && (
        <div role="alert" className="mb-3 rounded border border-line bg-bg p-3 text-[12.5px] text-warn">{finishedError}</div>
      )}

      <div className="min-h-[360px]">
        <QueryCard query={info} title="Saved runs">
          {() => shown
            ? <ResultView id={shown} />
            : <EmptyState>No saved runs yet. Click <b>New backtest</b> to run one.</EmptyState>}
        </QueryCard>
      </div>
    </div>
  )
}
