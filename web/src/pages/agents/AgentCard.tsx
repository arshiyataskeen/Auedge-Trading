import { useState, type KeyboardEvent, type ReactNode } from 'react'
import type { AgentView, Analysis } from '../../api/types'
import Modal from '../../components/Modal'
import { price } from '../../lib/format'
import { Bias } from '../dashboard/Cards'
import { KIND_BAR, KIND_TEXT, MOOD_CLS, agentLabel, cls, hitRate } from './logic'

/** Thin confidence bar (old .confbar). */
export function ConfBar({ pct, kind = 'WAIT' }: { pct: number; kind?: keyof typeof KIND_BAR }) {
  return (
    <div className="h-[3px] overflow-hidden rounded-sm bg-panel2">
      <span className={`block h-full ${KIND_BAR[kind]}`} style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  )
}

/** Old weightText(). */
export function WeightText({ r, perfOn }: { r: AgentView; perfOn: boolean }): ReactNode {
  if (r.vote_off) return <><span className="text-warn">Vote OFF</span> (review board / you) · still shows its view and levels</>
  const p = r.perf
  if (!p || p.n < 100) return <>Vote weight {r.weight} · performance: {p ? p.n : 0} of 100 scored calls so far</>
  return perfOn
    ? <>Vote weight {r.base_weight} × {p.mult.toFixed(2)} = <b>{r.weight}</b> (right {p.hit_rate}% of {p.n} calls, 60 days)</>
    : <>Vote weight {r.weight} (fixed) · performance would give ×{p.mult.toFixed(2)} (right {p.hit_rate}% of {p.n})</>
}

const CLAMP3 = { display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 3, overflow: 'hidden' } as const

/** One agent tile (old #agentCards .tile). Opens its details with a click, Enter or Space. */
export function AgentCard({ r, d, onOpen }: { r: AgentView; d: Analysis; onOpen: () => void }) {
  const label = agentLabel(r), kind = cls(label)
  const key = (e: KeyboardEvent) => {
    if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onOpen() }
  }
  const dot = { BUY: 'bg-up', SELL: 'bg-down', NA: 'bg-warn', WAIT: 'bg-faint' }[kind]
  return (
    <div data-testid="agent-card" role="button" tabIndex={0} title="Click for full details" onClick={onOpen} onKeyDown={key}
      className="flex min-w-0 cursor-pointer flex-col gap-[5px] border-b border-line bg-panel px-3 py-2.5 text-text hover:bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent">
      <div className="flex items-center justify-between gap-1.5">
        <span className="flex items-center gap-2 text-[13.5px] font-semibold"><i className={`h-[7px] w-[7px] rounded-full ${dot}`} />{r.label}</span>
        <Bias kind={kind}>{label}</Bias>
      </div>
      <ConfBar pct={r.confidence} kind={kind === 'WAIT' || kind === 'NA' ? 'WAIT' : kind} />
      <div className="text-[11.5px] text-muted">{r.subtitle || r.timeframe} · confidence {r.confidence}% · {hitRate(d.track, r.agent)}</div>
      {r.base_weight ? <div className="text-[11.5px] text-muted"><WeightText r={r} perfOn={d.perf_weights_on} /></div> : null}
      <div className="text-[12.5px] leading-[1.4]" style={CLAMP3}>{r.summary || r.headline || (r.reasons || []).join(' ')}</div>
    </div>
  )
}

/** Old crowdCard(): the Panic .. Euphoria gauge from the sentiment agent. Renders nothing unless that agent is OK. */
export function CrowdCard({ a }: { a: AgentView | undefined }) {
  if (!a || a.status !== 'OK') return null
  const mood = String(a.metrics.mood ?? '')
  const g = +a.metrics.greed || 0
  const pos = Math.max(2, Math.min(98, ((g + 6) / 13) * 100)) // score -6..+7 -> 0..100%
  return (
    <section aria-label="Market psychology" className="rounded border border-line bg-panel p-3">
      <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-[.06em] text-muted">Market psychology · how the crowd is behaving</h2>
      <div className="mb-2 flex flex-wrap items-center gap-2.5">
        <b className={`text-[20px] font-extrabold tracking-[.02em] ${KIND_TEXT[MOOD_CLS[mood] || 'WAIT']}`}>{mood}</b>
        <Bias kind={cls(a.bias)}>{a.bias === 'WAIT' ? 'No contrarian trade' : 'Leans ' + a.bias}</Bias>
      </div>
      <div className="relative h-2 rounded"
        style={{ background: 'linear-gradient(90deg, #f23645, #ff9800 30%, #5d606b 50%, #ff9800 70%, #089981)' }}>
        <span className="absolute -top-1 -ml-0.5 h-4 w-1 rounded-sm bg-text shadow-[0_0_0_2px_var(--bg)]" style={{ left: `${pos}%` }} />
      </div>
      <div className="mt-1 flex justify-between text-[10.5px] text-muted"><span>Panic</span><span>Fear</span><span>Neutral</span><span>Greed</span><span>Euphoria</span></div>
      <div className="my-2 text-[12.5px] leading-[1.45] text-text">{a.summary}</div>
      <div>
        {a.rows.slice(1).map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 border-b border-dashed border-line py-1 text-[12.5px]">
            <span className="whitespace-nowrap text-muted">{k}</span><b className="text-right font-medium">{v}</b>
          </div>
        ))}
      </div>
    </section>
  )
}

const List = ({ items, tone = '' }: { items: string[] | undefined; tone?: string }) =>
  items && items.length ? <ul className={`mt-2 list-disc pl-5 text-[12.5px] ${tone}`}>{items.map((x, i) => <li key={i}>{x}</li>)}</ul> : null

/** Old openDetails(<agent index>): rows, summary, warnings and levels of one agent, in a dialog. */
export function AgentDetails({ r, d, onClose }: { r: AgentView; d: Analysis; onClose: () => void }) {
  const label = agentLabel(r)
  return (
    <Modal label={`${r.label} details`} onClose={onClose}>
      <h2 className="mb-1 pr-8 text-[15px] font-semibold text-strong">
        {r.label} <Bias kind={cls(label)}>{label}</Bias>{' '}
        <span className="text-[12px] font-normal text-muted">{r.subtitle || r.timeframe} · confidence {r.confidence}% · {hitRate(d.track, r.agent)}</span>
      </h2>
      {r.rows?.length > 0 && (
        <table className="mt-2 w-full border-collapse text-[12.5px]">
          <tbody>
            {r.rows.map(([k, v], i) => (
              <tr key={i} className="border-t border-line align-top">
                <td className="w-[30%] py-[5px] pr-2.5 text-muted">{k}</td><td className="py-[5px] text-right">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="mt-3 text-[13px] leading-[1.5] text-text">{r.summary || r.headline}</div>
      {r.status !== 'OK' && <List items={r.reasons} tone="text-warn" />}
      <List items={r.warnings} tone="text-warn" />
      {r.levels?.length > 0 && (
        <table className="mt-2 w-full border-collapse text-[12.5px]">
          <tbody>
            {r.levels.map((l, i) => (
              <tr key={i} className="border-t border-line">
                <td className="py-[5px]">{l.kind}{l.note ? <span className="text-[11.5px] text-muted"> · {l.note}</span> : null}</td>
                <td className="py-[5px] text-right font-semibold tabular-nums">{price(l.price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Modal>
  )
}

/** Cards grid + details dialog state. */
export default function AgentGrid({ d }: { d: Analysis }) {
  const [open, setOpen] = useState<number | null>(null)
  return (
    <>
      <div className="grid grid-cols-1 overflow-hidden rounded border border-b-0 border-line sm:grid-cols-2 xl:grid-cols-3">
        {d.agents.map((r, i) => <AgentCard key={r.agent} r={r} d={d} onOpen={() => setOpen(i)} />)}
      </div>
      {open != null && d.agents[open] && <AgentDetails r={d.agents[open]} d={d} onClose={() => setOpen(null)} />}
    </>
  )
}
