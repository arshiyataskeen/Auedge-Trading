import { Link } from 'react-router-dom'
import type { Analysis, StopPool } from '../../api/types'
import { price } from '../../lib/format'
import NewsIntelCard, { newsIntelProps } from '../../components/NewsIntelCard'
import { CrowdCard } from '../agents/AgentCard'
import { LABELS, cls } from '../agents/logic'
import { Card, Sect } from '../journal/ui'
import PsychCard, { useMyDay } from './Psych'

const TONE = { BUY: 'border-t-2 border-t-up', SELL: 'border-t-2 border-t-down', NA: '', WAIT: '' }
const BTONE = { BUY: 'text-up', SELL: 'text-down', NA: 'text-warn', WAIT: 'text-text' }
const CHIP = { BUY: 'bg-up-bg text-up', SELL: 'bg-down-bg text-down', NA: 'bg-warn-bg text-warn', WAIT: 'bg-panel2 text-muted' }

/** Old poolLine(): one stop pool with a strength bar. */
function Pool({ p }: { p: StopPool }) {
  return (
    <div className="flex items-center gap-2 overflow-hidden whitespace-nowrap py-px text-[12.5px]" title={p.sources.join(', ')}>
      <b className="min-w-[70px] tabular-nums">{price(p.price)}</b>
      <span className="h-[5px] max-w-[90px] flex-none rounded-sm bg-warn opacity-80" style={{ width: `${Math.min(100, p.strength * 9)}%` }} />
      {p.status === 'hunted' && <span className="text-[11px] text-muted">hunted {p.hunted_ago_min}m ago</span>}
    </div>
  )
}
const None = () => <div className="text-[11.5px] text-muted">none near</div>

/** The old Plan tab: journal button, crowd mood, discipline coach, timeframes, what to do, agent vote, stop map and the Chief's reasoning. */
export default function PlanPanel({ d }: { d: Analysis }) {
  const c = d.chief, plan = c.plan, p = c.price, dc = d.data_check
  const { myStop } = useMyDay()
  const userStop = !dc.veto && myStop && plan.kind !== 'none'
  const ok = d.agents.filter((a) => a.status === 'OK' && a.agent !== 'psychology')
  const psy = d.agents.find((a) => a.agent === 'psychology'), crowd = d.agents.find((a) => a.agent === 'sentiment')
  const nBuy = ok.filter((a) => a.bias === 'BUY').length, nSell = ok.filter((a) => a.bias === 'SELL').length
  const nWait = ok.length - nBuy - nSell, w = (n: number) => (ok.length ? (100 * n) / ok.length : 0)
  return (
    <div className="flex flex-col gap-2 pt-2">
      {plan.kind === 'now' && (
        <Link to="/journal?call=1" className="block rounded border border-accent bg-accent px-3 py-2 text-center text-[13px] font-semibold text-white no-underline hover:opacity-90">
          ＋ Add this {plan.side} NOW call to my journal
        </Link>
      )}
      <CrowdCard a={crowd} />
      <NewsIntelCard compact {...newsIntelProps(d.agents)} />
      <PsychCard psy={psy} plan={plan} genAt={d.generated_at} userStop={userStop} />
      <Card label="Timeframes">
        <Sect>Timeframes · Daily to 15m</Sect>
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          {c.timeframes.map((x) => (
            <div key={x.tf} className={`min-w-0 rounded bg-panel2 px-2 py-[7px] ${TONE[cls(x.bias)]}`}>
              <div className="text-[11px] text-muted">{x.tf} · {x.weight}%{x.role === 'pullback' ? ' · pullback' : ''}</div>
              <div className={`text-[14px] font-bold ${BTONE[cls(x.bias)]}`}>{x.bias}</div>
              <div className="line-clamp-2 text-[11.5px] leading-[1.3] text-muted">{x.text}</div>
            </div>
          ))}
        </div>
      </Card>
      <Card label="What to do">
        <Sect>What to do</Sect>
        <ol className="ml-[18px] list-decimal text-[13px]">{plan.steps.map((s, i) => <li key={i} className="my-[3px]">{s}</li>)}</ol>
        {plan.cancel_if && <div className="mt-1.5 text-[12px] text-muted">Cancel: {plan.cancel_if}</div>}
      </Card>
      <Card label="Agent vote">
        <Sect>Agent vote · {nBuy} buy · {nWait} wait · {nSell} sell</Sect>
        <div className="mb-2 flex h-1.5 gap-0.5" aria-hidden="true">
          <span className="block rounded-sm bg-up" style={{ width: `${w(nBuy)}%` }} />
          <span className="block rounded-sm bg-hover" style={{ width: `${w(nWait)}%` }} />
          <span className="block rounded-sm bg-down" style={{ width: `${w(nSell)}%` }} />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {c.chips.map((ch) => (
            <span key={ch.agent} title={ch.label} className={`whitespace-nowrap rounded px-[7px] py-0.5 text-[11.5px] font-semibold ${CHIP[cls(ch.label)]}`}>
              {LABELS[ch.agent] || ch.agent}: {ch.label}
            </span>
          ))}
        </div>
      </Card>
      <Card label="Stop map">
        <div title="Where stop losses are likely resting. Longer bar = more stops. Price is often pulled toward them.">
          <Sect>Where stops are resting</Sect>
          <div className="my-0.5 text-[11px] text-muted">Buy stops above</div>
          {c.stops_above.length ? c.stops_above.slice(0, 3).reverse().map((x, i) => <Pool key={i} p={x} />) : <None />}
          <div className="my-1 border-y border-dashed border-accent py-0.5 text-center text-[12px] text-accent">price {p ? price(p) : '—'}</div>
          {c.stops_below.length ? c.stops_below.slice(0, 3).map((x, i) => <Pool key={i} p={x} />) : <None />}
          <div className="my-0.5 text-[11px] text-muted">Sell stops below</div>
        </div>
      </Card>
      <Card label="Chief's reasoning">
        <Sect>Chief's reasoning</Sect>
        <div className="text-[13px] leading-[1.5]">
          {c.verdict}{c.ai_written && <span className="ml-2 rounded bg-acc-bg px-1.5 py-px text-[10.5px] text-accent">by Claude</span>}
        </div>
      </Card>
    </div>
  )
}
