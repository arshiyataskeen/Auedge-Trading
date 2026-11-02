import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useAnalysis, useDemo, useIntelFlags } from '../../api/endpoints'
import type { Analysis, AgentView, Demo, IntelFlag } from '../../api/types'
import { price } from '../../lib/format'
import ChiefDetails from '../trade/ChiefDetails'
import { AgentDetails } from './AgentCard'
import { agentLabel, cls, labelOf } from './logic'

const TONE = { BUY: 'text-up bg-up-bg', SELL: 'text-down bg-down-bg', NA: 'text-warn bg-warn-bg', WAIT: 'text-muted bg-panel2' }
const DATA = ['Gold spot / futures', 'DXY, silver, S&P', 'Treasury yields', 'News calendar']
const STEP_MS = 450

type Sel = { kind: 'agent'; r: AgentView } | { kind: 'chief' } | null

function Node({ title, children, off, active, onOpen, id }: {
  title: string; children?: ReactNode; off?: boolean; active: boolean; onOpen?: () => void; id?: string
}) {
  const base = `block rounded border p-2 text-[12px] ${off ? 'bg-panel2 text-muted' : 'bg-panel text-text'} ${active ? 'border-accent' : 'border-line'}`
  const head = <b className={`text-strong ${off ? 'line-through' : ''}`}>{title}</b>
  if (!onOpen) return <div data-testid="flow-node" data-id={id} className={base}>{head}{children}</div>
  return (
    <button type="button" data-testid="flow-node" data-id={id} data-off={off ? 'true' : undefined} onClick={onOpen}
      className={`${base} w-full cursor-pointer text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent`}>
      {head}{children}
    </button>
  )
}

function Chip({ kind, children }: { kind: keyof typeof TONE; children: ReactNode }) {
  return <span className={`ml-1 rounded px-1.5 py-px text-[11px] font-semibold ${TONE[kind]}`}>{children}</span>
}

function Stage({ n, label, step, running, last, children }: { n: number; label: string; step: number; running: boolean; last?: boolean; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col md:flex-row" data-stage={n}>
      <section aria-label={label} className="flex min-w-0 flex-1 flex-col gap-1.5">
        <h3 className="text-[11px] font-semibold uppercase tracking-[.06em] text-muted">{label}</h3>
        {children}
      </section>
      {!last && (
        <div aria-hidden className="flex items-center justify-center py-1 md:px-1 md:py-0" style={{ minWidth: 30, minHeight: 22 }}>
          <span className="h-5 w-px bg-line2 md:h-px md:w-5" />
          {running && step === n && <i className="flow-dot absolute h-1.5 w-1.5 rounded-full bg-accent" />}
        </div>
      )}
    </div>
  )
}

export function FlowView({ d, flags, demo }: { d: Analysis; flags: IntelFlag[]; demo: Demo | undefined }) {
  const reduced = typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const [run, setRun] = useState(0)
  const [step, setStep] = useState(reduced ? 99 : 0)
  const [sel, setSel] = useState<Sel>(null)
  const first = useRef(true)
  // A new analysis restarts the run.
  useEffect(() => { if (first.current) { first.current = false; return } setRun((n) => n + 1) }, [d.generated_at])
  useEffect(() => {
    if (reduced) { setStep(99); return }
    setStep(0)
    const t = setInterval(() => setStep((s) => (s >= 7 ? 99 : s + 1)), STEP_MS)
    return () => clearInterval(t)
  }, [run, reduced])
  const running = step < 99, act = (n: number) => running && step === n

  const stage1 = d.agents.filter((a) => a.agent !== 'skeptic' && a.agent !== 'psychology')
  const skeptic = d.agents.find((a) => a.agent === 'skeptic')
  const coach = d.agents.find((a) => a.agent === 'psychology')
  const c = d.chief, q = c.quality, plan = c.plan
  const pos = demo?.open?.[0]
  const phase = (a: AgentView) => (a.extra as { phase?: string } | undefined)?.phase
  const agentNode = (a: AgentView, n: number) => {
    const lab = agentLabel(a), k = cls(lab)
    return (
      <Node key={a.agent} id={a.agent} title={a.label || labelOf(a.agent)} off={a.vote_off} active={act(n)} onOpen={() => setSel({ kind: 'agent', r: a })}>
        <Chip kind={a.vote_off ? 'WAIT' : k}>{lab}</Chip><span className="ml-1 text-muted">{a.confidence}%</span>
        {a.vote_off && <span className="block text-warn">Vote off</span>}
        {a.agent === 'news_intel' && phase(a) && <span className="block text-muted">Card: {phase(a) === 'post' ? 'after release' : 'before release'}</span>}
      </Node>
    )
  }
  return (
    <div data-testid="flow" data-run={run} data-static={reduced ? 'true' : undefined} className="relative flex flex-col gap-3 pt-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[12.5px] text-muted">Data goes in, agents vote, the Chief decides, the filters check it, and a plan comes out. Click a box for details.</p>
        <button type="button" onClick={() => setRun((n) => n + 1)} className="rounded border border-line bg-panel px-3 py-1 text-[12px] text-strong hover:bg-hover">Replay</button>
      </div>
      <div className="flex flex-col gap-1 md:flex-row md:gap-0">
        <Stage n={0} label="Data" step={step} running={running}>
          {DATA.map((x) => <Node key={x} title={x} active={act(0)} />)}
        </Stage>
        <Stage n={1} label="Agents" step={step} running={running}>{stage1.map((a) => agentNode(a, 1))}</Stage>
        <Stage n={2} label="Skeptic" step={step} running={running}>
          {skeptic ? agentNode(skeptic, 2) : <Node title="Skeptic" active={act(2)} />}
        </Stage>
        <Stage n={3} label="Chief" step={step} running={running}>
          <Node id="chief" title="Chief" active={act(3)} onOpen={() => setSel({ kind: 'chief' })}>
            <Chip kind={cls(c.bias)}>{c.bias}</Chip><span className="ml-1 text-muted">{c.confidence}%</span>
            {q && <span className="block">Setup quality {q.score} · {q.band}{q.avoid ? ' · AVOID' : ''}</span>}
          </Node>
        </Stage>
        <Stage n={4} label="Gates" step={step} running={running}>
          {coach && agentNode(coach, 4)}
          {flags.length ? flags.map((f) => (
            <Node key={f.name} id={`flag-${f.name}`} title={f.name} off={!f.on} active={act(4)}>
              <span className="block text-muted">{f.on ? 'On' : 'Off'}</span>
            </Node>
          )) : <Node title="News gates" active={act(4)}><span className="block text-muted">No flag data</span></Node>}
        </Stage>
        <Stage n={5} label="Plan" step={step} running={running}>
          <Node id="plan" title={plan.action || 'NO TRADE'} active={act(5)}>
            {plan.stop != null && (
              <span className="block tabular-nums text-muted">
                Entry {price(plan.entry_lo)}–{price(plan.entry_hi)} · Stop {price(plan.stop)} · Target {price(plan.t1)}
              </span>
            )}
          </Node>
        </Stage>
        <Stage n={6} label="Demo account" step={step} running={running} last>
          <Node id="demo" title="Demo account" active={act(6)}>
            <span className="block text-muted">{pos ? `${pos.side} open at ${price(pos.entry)}` : 'Waiting'}</span>
          </Node>
        </Stage>
      </div>
      {sel?.kind === 'agent' && <AgentDetails r={sel.r} d={d} onClose={() => setSel(null)} />}
      {sel?.kind === 'chief' && <ChiefDetails d={d} onClose={() => setSel(null)} />}
    </div>
  )
}

export default function Flow() {
  const a = useAnalysis(), f = useIntelFlags(), dm = useDemo()
  if (!a.data) return <p className="pt-3 text-muted">Loading the latest analysis…</p>
  return <FlowView d={a.data} flags={f.data?.flags ?? []} demo={dm.data} />
}
