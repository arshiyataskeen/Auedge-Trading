import type { ReactNode } from 'react'
import type { Analysis, StopPool } from '../../api/types'
import Modal from '../../components/Modal'
import { price } from '../../lib/format'
import { Bias } from '../dashboard/Cards'
import { LABELS, cls } from '../agents/logic'
import { inputCls } from '../journal/ui'
import { SizeLine } from './Decision'
import { useStored } from './logic'

const Rows = ({ rows }: { rows: [ReactNode, ReactNode][] }) => (
  <table className="mt-2 w-full border-collapse text-[12.5px]">
    <tbody>
      {rows.map(([k, v], i) => (
        <tr key={i} className="border-t border-line align-top">
          <td className="w-[30%] py-[5px] pr-2.5 text-muted">{k}</td><td className="py-[5px] text-right">{v}</td>
        </tr>
      ))}
    </tbody>
  </table>
)
const H = ({ children }: { children: ReactNode }) => <h3 className="mb-0 mt-3.5 text-[14px] font-semibold text-strong">{children}</h3>
const List = ({ items, tone = '' }: { items: string[]; tone?: string }) =>
  items.length ? <ul className={`mt-2 list-disc pl-5 text-[12.5px] ${tone}`}>{items.map((x, i) => <li key={i}>{x}</li>)}</ul> : null
const PLAN_TONE = { BUY: 'border-l-up', SELL: 'border-l-down', NA: 'border-l-warn', WAIT: 'border-l-line2' }

/** Old openDetails("chief"): the full plan, position-size calculator, timeframes, stop-loss map and track record. */
export default function ChiefDetails({ d, onClose }: { d: Analysis; onClose: () => void }) {
  const c = d.chief, plan = c.plan, tr = d.track
  const [acct, setAcct] = useStored('acct', '1000'), [risk, setRisk] = useStored('riskPct', '1')
  const pools = (arr: StopPool[], name: string): [ReactNode, ReactNode][] => arr.map((p) => [
    `${name}: ${price(p.price)}`,
    `strength ${p.strength}${p.status === 'hunted' ? ` · HUNTED ${p.hunted_ago_min} min ago` : ' · untouched'} · ${p.sources.join(', ')}`,
  ])
  return (
    <Modal label="Chief analyst details" onClose={onClose}>
      <h2 className="mb-1 flex flex-wrap items-center gap-1.5 pr-8 text-[15px] font-semibold text-strong">
        Chief analyst <Bias kind={cls(c.htf_label)}>{c.htf_label}</Bias> <Bias kind={cls(c.intraday_label)}>{c.intraday_label}</Bias>
        <span className="text-[12px] font-normal text-muted">confidence {c.confidence_word} ({c.confidence}%)</span>
      </h2>
      <div className={`mt-2 rounded border border-line border-l-[3px] bg-bg p-3 ${PLAN_TONE[cls(plan.action)]}`}>
        <div className="text-[18px] font-extrabold text-strong">{plan.action}</div>
        <ol className="ml-[18px] mt-1 list-decimal text-[13px]">{plan.steps.map((s, i) => <li key={i} className="my-0.5">{s}</li>)}</ol>
        {plan.cancel_if && <div className="mt-1 text-[11.5px] text-muted">Cancel: {plan.cancel_if}</div>}
        {plan.stop != null && (
          <Rows rows={[
            ['Entry', <b key="e">{price(plan.entry_lo)} – {price(plan.entry_hi)}</b>],
            ['Stop loss', <b key="s">{price(plan.stop)}</b>],
            ...(plan.t1 != null ? [['Target 1', <b key="t">{price(plan.t1)}{plan.rr1 ? ` (reward ${plan.rr1}× risk)` : ''}</b>] as [ReactNode, ReactNode]] : []),
            ...(plan.be_at != null ? [['Half off at 1R', <b key="b">{price(plan.be_at)} (then move the stop to the entry)</b>] as [ReactNode, ReactNode]] : []),
          ]} />
        )}
        <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[12.5px]">
          <label className="flex items-center gap-1.5">Account $
            <input type="number" min="0" value={acct} onChange={(e) => setAcct(e.target.value)} className={`${inputCls} w-24`} /></label>
          <label className="flex items-center gap-1.5">Risk %
            <input type="number" min="0.1" step="0.1" value={risk} onChange={(e) => setRisk(e.target.value)} className={`${inputCls} w-16`} /></label>
        </div>
        <div className="mt-1.5 text-[12.5px]"><SizeLine plan={plan} /></div>
      </div>
      <div className="mt-3 text-[13px] leading-[1.5]">
        {c.verdict}{c.ai_written && <span className="ml-2 rounded bg-acc-bg px-1.5 py-px text-[10.5px] text-accent">written by Claude from the agents' findings</span>}
      </div>
      <Rows rows={c.timeframes.map((t) => [`${t.tf} (${t.weight}%): ${t.bias}${t.role === 'pullback' ? ' · pullback' : ''}`, t.text])} />
      <H>Stop-loss map</H>
      <Rows rows={[...pools(c.stops_above.slice().reverse(), 'Buy stops'), ...pools(c.stops_below, 'Sell stops')]} />
      <H>Track record</H>
      {tr && (
        <Rows rows={Object.entries(tr.agents).map(([k, a]) => [
          LABELS[k] || (k === 'chief' ? 'Chief direction' : k),
          `${a.hit_rate != null ? `${a.hit_rate}% right` : 'not scored yet'} · ${a.hits} right, ${a.misses} wrong, ${a.flat} flat, ${a.pending} waiting`,
        ])} />
      )}
      {tr?.trades?.recent?.length ? (
        <>
          <H>Recent Chief trades</H>
          <Rows rows={tr.trades.recent.map((t) => [
            `${new Date(t.ts * 1000).toLocaleString()} · ${t.side}`,
            <>entry {price(t.entry)} · stop {price(t.stop)} · target {price(t.t1)} · <b>{t.status}</b>{t.result_r != null ? ` (${t.result_r}R)` : ''}</>,
          ])} />
        </>
      ) : null}
      <div className="mt-2 text-[11.5px] text-muted">
        Agents are scored 4 hours after each call (right = price moved at least $3 their way). Calls repeat every 15 minutes, so counts grow quickly and are not independent trades. Past results do not guarantee future results.
      </div>
      <List items={c.reasons} />
      <List items={c.warnings} tone="text-warn" />
    </Modal>
  )
}
