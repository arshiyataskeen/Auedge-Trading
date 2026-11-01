import { useSearchParams } from 'react-router-dom'
import { useAnalysis } from '../../api/endpoints'
import type { Analysis } from '../../api/types'
import PageHeader from '../../components/PageHeader'
import QueryCard from '../../components/QueryCard'
import Tabs from '../../components/Tabs'
import AgentGrid from './AgentCard'
import ReviewBoard from './ReviewBoard'
import TrackRecord from './TrackRecord'
import TradeReviewer from './TradeReviewer'

const TABS = [{ key: 'agents', label: 'Agents' }, { key: 'track', label: 'Track record' }]

/** Old aStatus line: when the analysis ran, the data check, Claude summary, adapter problems. */
function Status({ d }: { d: Analysis }) {
  const dc = d.data_check
  return (
    <>
      Updated {new Date(d.generated_at).toLocaleTimeString()} · data: <b className={dc.veto ? 'text-warn' : ''}>{dc.headline}</b>
      {d.ai_enabled ? ' · Claude summary on' : ''}
      {d.adapter_problems.length ? ` · adapter problems: ${d.adapter_problems.join('; ')}` : ''}
      {' · click any agent for details'}
    </>
  )
}

/** /agents: review board, trade reviewer and agent cards; the "Track record" tab (old Track tab) holds weights and scored calls. */
export default function AgentsPage() {
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') === 'track' ? 'track' : 'agents'
  const analysis = useAnalysis()
  const onTab = (k: string) => setSp((p) => { if (k === 'track') p.set('tab', 'track'); else p.delete('tab'); return p }, { replace: true })

  return (
    <div>
      <PageHeader title="Agents" subtitle={analysis.data ? <Status d={analysis.data} /> : undefined} />
      <Tabs items={TABS} value={tab} onChange={onTab} label="Agents sections">
        <div className="flex flex-col gap-3 pt-3">
          <ReviewBoard />
          <TradeReviewer />
          <QueryCard query={analysis} title="Agents">
            {(d) => <AgentGrid d={d} crowd={d.agents.find((a) => a.agent === 'sentiment')} />}
          </QueryCard>
        </div>
        <div className="pt-3">
          <QueryCard query={analysis} title="Track record">{(d) => <TrackRecord d={d} />}</QueryCard>
        </div>
      </Tabs>
    </div>
  )
}
