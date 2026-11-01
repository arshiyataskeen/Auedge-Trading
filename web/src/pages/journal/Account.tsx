import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAdvancePhase, useDemo, useJournalAccount, useJournalAccounts, useReopenPhase, useUpdateAccount } from '../../api/endpoints'
import type { JournalAccount, JournalTrade, Phase } from '../../api/types'
import EquityChart from '../../components/EquityChart'
import MoneyText from '../../components/MoneyText'
import PageHeader from '../../components/PageHeader'
import QueryCard from '../../components/QueryCard'
import Tabs from '../../components/Tabs'
import { money, toneOf } from '../../lib/format'
import { Bias, Meters, STATUS, TONE, usd } from '../dashboard/Cards'
import { lsGet, lsSet } from '../backtest/ui'
import AccountForm from './AccountForm'
import Consistency from './Consistency'
import JCalendar from './JCalendar'
import { jDay } from './logic'
import RiskReward from './RiskReward'
import TradeForm from './TradeForm'
import { Alert, btnCls, btnPrimaryCls, Card, DayBars, linkBtn, Meta, Sect, Stat, TradeTable } from './ui'

const SUBS = [{ key: 'journal', label: 'Journal' }, { key: 'calendar', label: 'Calendar' }, { key: 'rr', label: 'Risk : Reward' }, { key: 'consistency', label: 'Consistency' }]

const B = ({ children }: { children: ReactNode }) => <b className="text-strong">{children}</b>
/** Old rulesText. */
function RulesText({ r }: { r: Phase['check']['rules'] }) {
  const parts: ReactNode[] = [r.target_pct != null ? <>Target <B>{r.target_pct}%</B></> : 'No target']
  if (r.daily_loss_pct) parts.push(<>Daily loss <B>{r.daily_loss_pct}%</B></>)
  if (r.max_loss_pct) parts.push(<>Max loss <B>{r.max_loss_pct}%</B> ({r.max_loss_type})</>)
  if (r.min_days) parts.push(<>Min <B>{r.min_days}</B> trading days</>)
  if (r.consistency_pct) parts.push(<>Best day ≤ <B>{r.consistency_pct}%</B> of profit</>)
  if (r.profit_split) parts.push(<>Profit split <B>{r.profit_split}%</B></>)
  return <>{parts.map((x, i) => <span key={i}>{i ? ' · ' : ''}{x}</span>)}</>
}

/** Old stepper: one button per phase plus Funded; only phases that exist can be picked. */
function Stepper({ a, sel, onPick }: { a: JournalAccount; sel: Phase; onPick: (id: number) => void }) {
  const names = [...a.rules.phases.map((p) => p.name), 'Funded']
  return (
    <ol className="mb-3 flex flex-wrap items-center gap-1 text-[12px]" aria-label="Phases">
      {names.map((n, i) => {
        const p = a.phases.find((x) => x.idx === i)
        const st = !p ? 'todo' : p.result === 'passed' ? 'done' : p.result === 'failed' ? 'fail' : 'now'
        const tone = st === 'done' ? 'border-up text-up' : st === 'fail' ? 'border-down text-down' : st === 'now' ? 'border-accent text-strong' : 'border-line text-muted'
        return (
          <li key={i} className="flex items-center gap-1">
            {i > 0 && <span className="h-px w-5 bg-line2" />}
            <button type="button" disabled={!p} aria-current={p && sel.id === p.id ? 'step' : undefined} onClick={() => p && onPick(p.id)}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${tone} ${p && sel.id === p.id ? 'bg-acc-bg' : 'bg-panel'} disabled:opacity-50`}>
              <i className="not-italic font-bold">{st === 'done' ? '✓' : st === 'fail' ? '✕' : i + 1}</i><span>{n}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

export default function JournalAccountPage() {
  const id = Number(useParams().accountId)
  const q = useJournalAccount(Number.isFinite(id) ? id : null)
  return (
    <QueryCard query={q} title="Account">
      {(a) => (a.error || !a.phases?.length
        ? <Card><p className="text-[12.5px] text-muted">{a.error || 'Account not found.'}</p><Link to="/dashboard" className={linkBtn}>← All accounts</Link></Card>
        : <AccountView a={a} />)}
    </QueryCard>
  )
}

type Form = { k: 'trade'; trade?: JournalTrade } | { k: 'edit' } | null

/** Port of openAccount / renderAccount. */
function AccountView({ a }: { a: JournalAccount }) {
  const nav = useNavigate()
  const all = useJournalAccounts(true)
  const demo = useDemo()
  const [phaseId, setPhaseId] = useState<number | null>(null)
  const [sub, setSub] = useState(() => { const v = lsGet('jSub', 'journal'); return SUBS.some((s) => s.key === v) ? v : 'journal' })
  const [form, setForm] = useState<Form>(null)
  const [err, setErr] = useState('')
  const advance = useAdvancePhase(), reopen = useReopenPhase(), update = useUpdateAccount()

  const p = a.phases.find((x) => x.id === phaseId) ?? a.current ?? a.phases[a.phases.length - 1]
  const c = p.check, s = c.stats
  const [sc, st] = STATUS[c.status] ?? ['NA' as const, c.status]
  const isCur = !p.result
  const last = a.phases[a.phases.length - 1]
  const trades = (a.trades ?? []).filter((t) => t.phase_id === p.id)
  const nextName = p.is_funded ? '' : (a.rules.phases[p.idx + 1]?.name ?? 'Funded')
  const isDemo = demo.data?.journal_account === a.id
  // the open account (fresher than the list) replaces its own list entry so the trade form sees its phases
  const pool = [a, ...(all.data?.accounts ?? []).filter((x) => x.id !== a.id)]
  const known = (a.trades ?? []).map((t) => t.setup).filter(Boolean)
  const phName = p.is_funded ? 'Funded' : p.name

  const run = async (fn: () => Promise<unknown>) => {
    setErr('')
    try { await fn(); setPhaseId(null) } catch (e) { setErr((e as Error).message) }
  }
  const mark = (what: 'passed' | 'failed') => {
    const note = window.prompt(`Mark ${p.is_funded ? 'the funded account' : p.name} as ${what}? Optional note (e.g. "firm confirmed on 3 Nov"):`, '')
    if (note === null) return
    let nb: number | null = null
    if (what === 'passed') {
      const v = window.prompt('Starting balance of the next phase ($):', String(a.size))
      if (v === null) return
      nb = +v || a.size
    }
    void run(() => advance.mutateAsync({ id: a.id, body: { result: what, note, next_balance: nb } }))
  }
  const undo = () => { if (window.confirm('Undo the last passed / failed mark?')) void run(() => reopen.mutateAsync(a.id)) }
  const archive = () => { setErr(''); update.mutate({ id: a.id, body: { name: a.name, firm: a.firm, notes: a.notes, archived: !a.archived } }, { onError: (e) => setErr(e.message) }) }
  const canUndo = (p.id === last.id && !!p.result) || (last.id !== p.id && last.idx === p.idx + 1 && !last.result)
  const cons = c.consistency

  return (
    <div>
      <div className="mb-1"><Link to="/dashboard" className={linkBtn}>← All accounts</Link></div>
      <PageHeader
        title={a.name}
        subtitle={<>{a.firm}{a.firm ? ' · ' : ''}{usd(a.size)} account · created {jDay(a.created_at)}{a.archived ? ' · archived' : ''}</>}
        actions={<>
          <Bias kind={sc}>{st}</Bias>
          {isDemo ? <Link to="/demo" className={`${btnPrimaryCls} no-underline`}>Live Demo tab →</Link>
            : <button type="button" className={btnPrimaryCls} onClick={() => setForm({ k: 'trade' })}>＋ Add trade</button>}
          <button type="button" className={btnCls} onClick={() => setForm({ k: 'edit' })}>Edit account</button>
          <button type="button" className={btnCls} disabled={update.isPending} onClick={archive}>{a.archived ? 'Unarchive' : 'Archive'}</button>
        </>} />
      <Stepper a={a} sel={p} onPick={setPhaseId} />
      <div className="grid grid-cols-1 gap-3 min-[900px]:grid-cols-[minmax(0,1fr)_minmax(340px,28%)]">
        <div className="flex min-w-0 flex-col gap-3">
          <Card>
            <Sect>{phName} · started {jDay(p.started_at)}{p.ended_at ? ` · ended ${jDay(p.ended_at)}` : ''}</Sect>
            <Meta cls="mb-2"><RulesText r={c.rules} /> · starting balance {usd(p.start_balance)}</Meta>
            <div className="flex flex-col gap-1.5">
              {c.breach && <Alert>⚠ {c.breach.text}. Check with your firm; most firms end the phase here.</Alert>}
              {c.status === 'need_days' && <Alert tone="up">Target reached. Trade on at least {c.min_days - c.days_traded} more day(s) to meet the minimum (small, safe trades).</Alert>}
              {c.status === 'target_reached' && isCur && <Alert tone="up">🎉 Target reached and minimum days met. Mark it passed once your firm confirms.</Alert>}
              {c.status === 'need_consistency' && (
                <Alert tone="warn">Target reached, but your best day is {cons.best_day_share}% of the profit (limit {cons.limit_pct}%).
                  About {usd(cons.profit_needed)} more profit, without another big day, brings it within the rule.</Alert>
              )}
              {err && <Alert>{err}</Alert>}
            </div>
            <div className="my-3 grid grid-cols-2 gap-3 min-[600px]:grid-cols-4">
              <Big k="Balance" v={usd(c.balance)} />
              <Big k="Profit this phase" v={<MoneyText v={c.profit} />} />
              {c.target_left != null && <Big k="Left to target" v={usd(c.target_left)} />}
              <Big k="Trading days" v={<>{c.days_traded}{c.min_days ? <span className="text-[12px] font-normal text-muted"> / {c.min_days}</span> : null}</>} />
            </div>
            <Meters a={a} c={c} />
            <div className="mt-3 flex flex-wrap gap-2">
              {isCur && (
                <>
                  {!p.is_funded && (
                    <button type="button" className={c.status === 'target_reached' ? btnPrimaryCls : btnCls} disabled={c.status === 'breached' || advance.isPending}
                      onClick={() => mark('passed')}>Mark {p.name} passed → start {nextName}</button>
                  )}
                  <button type="button" className={btnCls} disabled={advance.isPending} onClick={() => mark('failed')}>Mark {p.is_funded ? 'account' : 'phase'} failed</button>
                </>
              )}
              {canUndo && <button type="button" className={btnCls} disabled={reopen.isPending} onClick={undo}>Undo {p.result || 'last'} mark</button>}
            </div>
            {p.note && <Meta cls="mt-2">Note: {p.note}</Meta>}
          </Card>
          <Tabs items={SUBS} value={sub} label="Journal views" onChange={(k) => { setSub(k); lsSet('jSub', k) }}>
            <div className="mt-3">
              <Card>
                <Sect>Journal · {phName} · newest first · click a trade to open it</Sect>
                {trades.length
                  ? <TradeTable trades={trades} plan onOpen={(t) => setForm({ k: 'trade', trade: t })} />
                  : <Meta>No trades in this phase yet. <button type="button" className={linkBtn} onClick={() => setForm({ k: 'trade' })}>Add your first trade</button></Meta>}
              </Card>
            </div>
            <div className="mt-3">
              <Card>
                <Sect>Calendar · {phName} · your firm's trading days</Sect>
                <JCalendar key={p.id} days={Object.fromEntries(c.days.map((d) => [d.day, d]))} trades={trades} onOpenTrade={(t) => setForm({ k: 'trade', trade: t })} />
              </Card>
            </div>
            <div className="mt-3"><RiskReward rr={c.rr} /></div>
            <div className="mt-3"><Consistency c={c} /></div>
          </Tabs>
        </div>
        <aside className="flex min-w-0 flex-col gap-3">
          <Card>
            <Sect>Stats · this phase</Sect>
            <div className="grid grid-cols-2 gap-2">
              <Stat v={s.n} k="closed trades" />
              <Stat v={s.win_rate != null ? `${s.win_rate}%` : '—'} k="win rate" />
              <Stat v={money(s.avg_win)} k="average win" tone="up" />
              <Stat v={money(s.avg_loss)} k="average loss" tone="dn" />
              <Stat v={s.profit_factor ?? '—'} k="profit factor" />
              <Stat v={s.avg_r != null ? `${s.avg_r}R` : '—'} k="average R" />
              <Stat v={money(s.best)} k="best" tone={toneOf(s.best)} />
              <Stat v={money(s.worst)} k="worst" tone={toneOf(s.worst)} />
            </div>
            {s.followed_plan_pct != null && (
              <Meta cls="mt-2">Followed the plan in <B>{s.followed_plan_pct}%</B> of trades: plan trades {money(s.followed_pnl)}, off-plan trades{' '}
                <span className={TONE[toneOf(s.broke_pnl)]}>{money(s.broke_pnl)}</span>.</Meta>
            )}
            {c.equity.length > 0 && <div className="mt-2"><EquityChart curve={c.equity} unit="$" /></div>}
          </Card>
          {c.days.length > 0 && <Card><Sect>Day by day</Sect><DayBars days={c.days.slice(-14).reverse()} /></Card>}
          {s.by_setup.length > 0 && (
            <Card><Sect>By setup</Sect>
              <table className="w-full text-[12px]"><tbody>
                {s.by_setup.map((x) => <tr key={x.setup}><td>{x.setup}</td><td className="text-muted">{x.n}</td><td className="text-muted">{x.win_rate}%</td>
                  <td className="text-right"><MoneyText v={x.pnl} /></td></tr>)}
              </tbody></table>
            </Card>
          )}
          {s.by_emotion.length > 0 && (
            <Card><Sect>By mood</Sect>
              <table className="w-full text-[12px]"><tbody>
                {s.by_emotion.map((x) => <tr key={x.emotion}><td>{x.emotion}</td><td className="text-muted">{x.n}</td><td className="text-right"><MoneyText v={x.pnl} /></td></tr>)}
              </tbody></table>
            </Card>
          )}
          {a.notes && <Card><Sect>Account notes</Sect><Meta cls="whitespace-pre-wrap">{a.notes}</Meta></Card>}
        </aside>
      </div>
      {form?.k === 'trade' && (
        <TradeForm trade={form.trade} accounts={pool} accountId={a.id} knownSetups={known as string[]} onClose={() => setForm(null)}
          onSaved={(b) => {
            if (b.account_id !== a.id) { if (typeof b.account_id === 'number') nav(`/journal/${b.account_id}`) } // moved to another account
            else if (typeof b.phase_id === 'number') setPhaseId(b.phase_id)
          }} />
      )}
      {form?.k === 'edit' && <AccountForm account={a} onClose={() => setForm(null)} onSaved={() => { /* queries refresh via invalidation */ }} />}
    </div>
  )
}

const Big = ({ k, v }: { k: string; v: ReactNode }) => (
  <div><div className="text-[11px] text-muted">{k}</div><div className="text-[20px] font-semibold tabular-nums text-strong">{v}</div></div>
)
