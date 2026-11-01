import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { Demo, JournalAccount, Phase, PhaseCheck } from '../../api/types'
import { money, toneOf } from '../../lib/format'

export const TONE = { up: 'text-up', dn: 'text-down', '': '' } as const
/** Whole-dollar amount without a sign (old jMoney). */
export const usd = (v: number | null | undefined) => money(v, { sign: false })

/** Old STATUS map: [badge colour, text]. */
export const STATUS: Record<string, [Side, string]> = {
  active: ['NA', 'In progress'], target_reached: ['BUY', 'Target reached ✓'], need_days: ['NA', 'Target hit · more days needed'],
  breached: ['SELL', 'Rule broken'], passed: ['BUY', 'Passed'], failed: ['SELL', 'Failed'],
  need_consistency: ['NA', 'Target hit · consistency rule'],
}
type Side = 'BUY' | 'SELL' | 'NA' | 'WAIT'

const BIAS: Record<Side, string> = {
  BUY: 'bg-up-bg text-up', SELL: 'bg-down-bg text-down', NA: 'bg-warn-bg text-warn', WAIT: 'bg-panel2 text-muted',
}
export function Bias({ kind, children }: { kind: Side; children: ReactNode }) {
  return <span className={`whitespace-nowrap rounded px-[7px] py-0.5 text-[11px] font-bold ${BIAS[kind]}`}>{children}</span>
}

const FILL = { tgt: 'bg-up', room: 'bg-entry', warnb: 'bg-warn' } as const
export function Bar({ pct, cls }: { pct: number; cls: keyof typeof FILL }) {
  return (
    <div className="mt-1 h-[7px] overflow-hidden rounded bg-panel2">
      <span className={`block h-full rounded ${FILL[cls]}`} style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  )
}

export function Meter({ label, value, sub, bar }: { label: string; value: ReactNode; sub?: ReactNode; bar?: ReactNode }) {
  return (
    <div className="mt-2">
      <div className="flex items-baseline justify-between gap-2 text-[12px]">
        <span className="text-muted">{label}</span>
        <b className="tabular-nums text-strong">{value}{sub != null && <> <span className="text-[11px] font-normal text-muted">{sub}</span></>}</b>
      </div>
      {bar}
    </div>
  )
}

/** A signed money value coloured up/down. */
export function Signed({ v }: { v: number | null | undefined }) {
  return <span className={`tabular-nums ${TONE[toneOf(v)]}`.trim()}>{money(v)}</span>
}

const CARD = 'block border-b border-r border-line bg-panel p-3 text-inherit no-underline hover:bg-panel2 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent'
/** The demo card's accent: green border + inset left bar (old .demoacard). */
const DEMO = CARD.replace('border-line', 'border-up') + ' shadow-[inset_3px_0_0_var(--up)]'
export const EMPTY = 'flex min-h-[160px] flex-col justify-center gap-1.5 border border-dashed border-line bg-panel p-3 text-inherit no-underline hover:bg-panel2'
const day = (ts: number | null | undefined) =>
  ts ? new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'

function Head({ title, sub, badge }: { title: string; sub: ReactNode; badge: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0"><b className="text-[14px] text-strong">{title}</b><div className="text-[11.5px] text-muted">{sub}</div></div>
      {badge}
    </div>
  )
}
export const Chip = ({ children }: { children: ReactNode }) => (
  <span className="rounded border border-line bg-panel2 px-1.5 py-0.5 text-[11px] text-strong">{children}</span>
)

export function Meters({ a, c }: { a: JournalAccount; c: PhaseCheck }) {
  const out: ReactNode[] = []
  if (c.target_amt != null) {
    out.push(<Meter key="t" label="Profit target" value={<span className={TONE[toneOf(c.profit)]}>{money(c.profit)}</span>} sub={`of ${usd(c.target_amt)}`}
      bar={<Bar pct={(100 * c.profit) / c.target_amt} cls="tgt" />} />)
  } else {
    out.push(<Meter key="t" label="Profit so far" value={<span className={TONE[toneOf(c.profit)]}>{money(c.profit)}</span>} />)
  }
  if (c.daily_limit != null) {
    const room = c.daily_room ?? 0
    out.push(<Meter key="d" label="Today's loss room" value={usd(c.daily_room)} sub={`of ${usd(c.daily_limit)}`}
      bar={<Bar pct={(100 * room) / c.daily_limit} cls={room < c.daily_limit * 0.35 ? 'warnb' : 'room'} />} />)
  }
  if (c.max_room != null) {
    const pct = c.rules.max_loss_pct ?? 0
    const full = Math.max(1, (pct / 100) * a.size) // the whole max-loss allowance in $
    out.push(<Meter key="m" label="Max loss room" value={usd(c.max_room)} sub={`above ${usd(c.max_floor)}`}
      bar={<Bar pct={(100 * c.max_room) / full} cls={c.max_room < 0.35 * full ? 'warnb' : 'room'} />} />)
  }
  return <>{out}</>
}

const phaseLabel = (a: JournalAccount, p: Phase) => (p.is_funded ? 'Funded' : `${p.name} of ${a.total_phases}`)

export function AccountCard({ a }: { a: JournalAccount }) {
  const p = a.current!, c = p.check
  const [kind, text] = STATUS[c.status] ?? ['NA' as Side, c.status]
  return (
    <Link to={`/journal/${a.id}`} aria-label={`Open ${a.name}`} data-testid="account-card" className={`${CARD} ${a.archived ? 'opacity-60' : ''}`}>
      <Head title={a.name} sub={`${a.firm || ''}${a.firm ? ' · ' : ''}${usd(a.size)} account`} badge={<Bias kind={kind}>{text}</Bias>} />
      <div className="mt-2 flex items-center justify-between gap-2 text-[11.5px] text-muted">
        <Chip>{phaseLabel(a, p)}</Chip><span>balance <b className="tabular-nums text-strong">{usd(c.balance)}</b></span>
      </div>
      {c.breach && <div className="mt-2 rounded bg-down-bg px-2 py-1 text-[12px] text-down">{c.breach.text}</div>}
      <Meters a={a} c={c} />
      <div className="mt-2 text-[11.5px] text-muted">
        {a.n_trades ?? 0} trades · {c.days_traded}{c.min_days ? ` of ${c.min_days}` : ''} trading days · last {a.last_trade_at ? day(a.last_trade_at) : 'none yet'}
      </div>
    </Link>
  )
}

export const DEMO_DAY_LOSS = 350, DEMO_DAY_PROFIT = 150 // the demo account's daily limits (Discipline coach)

/** `dm` already has live-price P&L applied (see withLivePrice). */
export function DemoCard({ dm, to }: { dm: Demo | undefined; to: string }) {
  const label = "Open the AuEdge demo account's journal"
  if (!dm) {
    return (
      <Link to={to} aria-label={label} className={DEMO}>
        <Head title="AuEdge Demo" sub="Automatic · loading…" badge={null} />
      </Link>
    )
  }
  const op = dm.open || []
  const pnl = Math.round((dm.equity - dm.start) * 100) / 100
  const fl = op.reduce((s, t) => s + (t.unrealised || 0), 0)
  const room = Math.max(0, DEMO_DAY_LOSS + Math.min(0, dm.today))
  const last = dm.closed?.length ? dm.closed[dm.closed.length - 1] : null
  const [kind, text]: [Side, string] = op.length ? ['BUY', 'Trade open']
    : dm.today <= -DEMO_DAY_LOSS ? ['SELL', 'Day stopped (loss limit)']
    : dm.today >= DEMO_DAY_PROFIT ? ['BUY', 'Day done (+$150 target)'] : ['NA', 'Waiting for a call']
  return (
    <Link to={to} aria-label={label} className={DEMO}>
      <Head title="AuEdge Demo" sub={`Automatic demo trading · ${usd(dm.start)} account · ${dm.lot} lot`} badge={<Bias kind={kind}>{text}</Bias>} />
      <div className="mt-2 flex items-center justify-between gap-2 text-[11.5px] text-muted">
        <Chip>AuEdge's own calls</Chip><span>balance <b className="tabular-nums text-strong">{usd(dm.balance)}</b></span>
      </div>
      <Meter label="Profit since start" value={<Signed v={pnl} />} />
      {op.length > 0 && <Meter label={`Open ${op[0].side} ${op[0].lot}`} value={<Signed v={Math.round(fl * 100) / 100} />} />}
      <Meter label="Today's loss room" value={usd(room)} sub={`of ${usd(DEMO_DAY_LOSS)}`}
        bar={<Bar pct={(100 * room) / DEMO_DAY_LOSS} cls={room < DEMO_DAY_LOSS * 0.35 ? 'warnb' : 'room'} />} />
      <Meter label="Today · this week" value={<><Signed v={dm.today} /> · <Signed v={dm.week} /></>} />
      <div className="mt-2 text-[11.5px] text-muted">
        {dm.trades} closed trades{dm.win_rate != null ? ` · ${dm.win_rate}% won` : ''} · last {last?.closed_ts ? day(last.closed_ts) : 'none yet'} · tap for its journal
      </div>
    </Link>
  )
}
