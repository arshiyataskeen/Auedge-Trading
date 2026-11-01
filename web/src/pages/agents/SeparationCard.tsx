import { useSeparation } from '../../api/endpoints'
import type { SeparationRow } from '../../api/types'
import QueryCard from '../../components/QueryCard'
import { Card, Meta, Sect } from '../journal/ui'
import { LABELS } from './logic'

const TH = 'px-1 py-1 text-left text-[10.5px] font-normal uppercase text-muted'
const TD = 'border-t border-line px-1 py-1.5 align-middle'
const VERDICT = {
  useful: { text: 'Useful', cls: 'bg-up-bg text-up' },
  none: { text: 'No clear signal', cls: 'bg-panel2 text-muted' },
  harmful: { text: 'Harmful', cls: 'bg-down-bg text-down' },
  too_few: { text: 'Too few calls', cls: 'bg-warn-bg text-warn' },
} as const

const f3 = (v: number | null) => (v == null ? '—' : v.toFixed(3))
const dist = (r: SeparationRow) => (r.lo == null || r.hi == null ? f3(r.distance) : `${f3(r.distance)} (${f3(r.lo)} to ${f3(r.hi)})`)
const name = (k: string) => LABELS[k] || (k === 'chief' ? 'Chief direction' : k)

function Chip({ v }: { v: SeparationRow['verdict'] }) {
  const c = VERDICT[v]
  return <span className={`whitespace-nowrap rounded px-[7px] py-0.5 text-[11px] font-bold ${c.cls}`}>{c.text}</span>
}
const drift = (r: SeparationRow) => (r.drift?.flag ? `Behaving differently lately (last 30 days ${f3(r.drift.recent_distance)} vs ${f3(r.drift.prior_distance)} before)` : '')

export function SeparationTable({ rows }: { rows: SeparationRow[] }) {
  return (
    <Card label="Signal separation">
      <Sect>Signal separation (does gold behave differently after this agent's calls?)</Sect>
      <div className="sm:hidden">
        {rows.map((r) => (
          <div key={r.agent} data-testid="sep-card" className="border-t border-line py-2 text-[12.5px]">
            <div className="flex items-center justify-between gap-2"><b className="text-strong">{name(r.agent)}</b><Chip v={r.verdict} /></div>
            <div className="mt-1 text-[11.5px] tabular-nums text-muted">
              {r.n} calls · distance {dist(r)} · right {r.hit_rate != null ? `${r.hit_rate}%` : '—'} · average move {f3(r.mean)}
            </div>
            {drift(r) && <div className="mt-0.5 text-[11.5px] text-warn">{drift(r)}</div>}
          </div>
        ))}
      </div>
      <table className="hidden w-full border-collapse text-[12.5px] sm:table">
        <thead>
          <tr><th className={TH}>Agent</th><th className={`${TH} text-right`}>Calls</th><th className={`${TH} text-right`}>Distance (90% range)</th>
            <th className={`${TH} text-right`}>Right</th><th className={`${TH} text-right`}>Avg move</th><th className={TH}>Verdict</th><th className={TH}>Lately</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.agent}>
              <td className={TD}><b>{name(r.agent)}</b></td>
              <td className={`${TD} text-right tabular-nums`}>{r.n}</td>
              <td className={`${TD} text-right tabular-nums`}>{dist(r)}</td>
              <td className={`${TD} text-right tabular-nums text-muted`}>{r.hit_rate != null ? `${r.hit_rate}%` : '—'}</td>
              <td className={`${TD} text-right tabular-nums text-muted`}>{f3(r.mean)}</td>
              <td className={TD}><Chip v={r.verdict} /></td>
              <td className={`${TD} text-[11.5px] text-warn`}>{drift(r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Meta cls="mt-1.5">
        Distance 0 means gold moves the same after the agent's calls as at a random time; bigger means different. Average move is in units of normal 4-hour movement
        (positive = gold went the agent's way). Ranges allow for calls that overlap in time. "Behaving differently lately" uses a 95% range, so a few false flags are expected across many agents. Analysis only: this never changes votes, weights or trades.
        Source: {rows[0]?.source ?? 'none'}.
      </Meta>
    </Card>
  )
}

export default function SeparationCard() {
  const q = useSeparation()
  return <QueryCard query={q} title="Signal separation">{(rows) => <SeparationTable rows={rows} />}</QueryCard>
}
