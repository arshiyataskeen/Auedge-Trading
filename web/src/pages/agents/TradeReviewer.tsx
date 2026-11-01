import type { ReactNode } from 'react'
import { useTradeReview } from '../../api/endpoints'
import type { ReviewedTrade, TradeReview } from '../../api/types'
import QueryCard from '../../components/QueryCard'
import { rtext, toneOf } from '../../lib/format'
import { Bias } from '../dashboard/Cards'
import { Card, Meta, Sect } from '../journal/ui'
import { LABELS, cls } from './logic'

const TONE = { up: 'text-up', dn: 'text-down', '': '' } as const
const pct = (x: number) => `${Math.round(x * 100)}%`
const TH = 'px-1 py-1 text-left text-[10.5px] font-normal uppercase text-muted'
const TD = 'border-t border-line px-1 py-1.5 align-middle'
const Sub = ({ children }: { children: string }) => <h3 className="mb-1.5 mt-2.5 text-[11px] font-semibold uppercase tracking-[.06em] text-muted">{children}</h3>
const COND: Record<string, string> = { trend: 'Trend', agreement: 'Agreement', session: 'Session', news: 'News during trade' }

/** Old trvLoad/trvRender: who suggested each finished trade, why it won or lost, what the winners share. */
export default function TradeReviewer() {
  const q = useTradeReview()
  return <QueryCard query={q} title="Trade reviewer">{(d) => (d.made_at ? <Body d={d} /> : null)}</QueryCard>
}

function Body({ d }: { d: TradeReview }) {
  const name = (a: string) => d.labels[a] || LABELS[a] || a
  const off = new Set(d.voting_off || [])
  const weak = d.agents.filter((a) => a.verdict === 'weak' && !off.has(a.agent))
  const verdict: Record<string, ReactNode> = {
    strong: <span className="rounded bg-up-bg px-1.5 py-0.5 text-[11.5px] font-semibold text-up">strong</span>,
    weak: <span className="rounded bg-down-bg px-1.5 py-0.5 text-[11.5px] font-semibold text-down">weak</span>,
    ok: <span className="rounded bg-panel2 px-1.5 py-0.5 text-[11.5px] font-semibold text-muted">ok</span>,
    'few trades': <span className="text-[11.5px] text-muted">few trades</span>,
  }
  const why = (rv: ReviewedTrade) =>
    (rv.reasons || []).map((k) => (rv.won ? d.win_text : d.reason_text)[k] || k).join('; ') || (rv.won ? 'plan worked' : 'no clear single cause')
  const row = (rv: ReviewedTrade, i: number) => (
    <li key={`${rv.t}-${i}`} className="mb-1.5">
      <Bias kind={cls(rv.side)}>{rv.side}</Bias>{' '}
      <span className="text-[11.5px] text-muted">{new Date(rv.t * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>{' '}
      <b className={`tabular-nums ${rv.won ? 'text-up' : 'text-down'}`}>{rv.won ? 'WON' : 'LOST'} {rtext(rv.r)}</b><br />
      <span className="text-[11.5px] text-muted">For: {rv.for.map(name).join(', ') || 'none'} · Against: {rv.against.map(name).join(', ') || 'none'}</span><br />
      {rv.won ? 'Why it worked' : 'Why it went wrong'}: {why(rv)}
    </li>
  )
  return (
    <Card label="Trade reviewer">
      <Sect>Trade reviewer · studies every win and every loss</Sect>
      <Meta cls="mb-2">
        After each finished trade it records who suggested it, who was against, and why it won or lost. Evidence: {d.n_live} live demo trade(s) + {d.n_backtest} backtest
        trades. It never changes the rules from one trade: an agent that keeps hurting (15+ trades, under 40% helped) sends the review board in early, and the
        board changes a vote only if 6 months of backtest prove it better.
      </Meta>
      {d.win_patterns.length > 0 && (
        <div><b className="text-up">What our wins have in common</b>
          <ul className="list-disc pl-5 text-[12.5px] leading-[1.5]">{d.win_patterns.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
      )}
      {d.lessons.length > 0
        ? <div><b className="text-down">What keeps losing</b>
          <ul className="list-disc pl-5 text-[12.5px] leading-[1.5]">{d.lessons.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
        : <Meta>No repeated loss pattern yet.</Meta>}
      {weak.length > 0 && (
        <div className="my-1.5 text-warn">
          Weak vote: {weak.map((a) => name(a.agent)).join(', ')}. The review board will re-test it (early run at most every 3 days); it changes only if the backtest proves it.
        </div>
      )}
      <Sub>Agent scorecard · did its vote help?</Sub>
      <table className="w-full border-collapse text-[12.5px]">
        <thead><tr><th className={TH}>Agent</th><th className={TH}>Helped</th><th className={TH}>Hurt</th><th className={TH}>Right</th><th className={TH}><span className="sr-only">Verdict</span></th></tr></thead>
        <tbody>
          {d.agents.map((a) => (
            <tr key={a.agent}>
              <td className={TD}>{name(a.agent)}{off.has(a.agent) && <span className="text-[11.5px] text-muted"> (vote off)</span>}</td>
              <td className={`${TD} font-semibold tabular-nums text-up`}>{a.helped}</td>
              <td className={`${TD} font-semibold tabular-nums text-down`}>{a.hurt}</td>
              <td className={`${TD} font-semibold tabular-nums`}>{pct(a.acc)}</td>
              <td className={TD}>{verdict[a.verdict] || ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Meta>Helped = it voted for a winner or against a loser. Hurt = for a loser or against a winner.</Meta>
      <Sub>What wins · win rate by condition</Sub>
      <table className="w-full border-collapse text-[12.5px]">
        <thead><tr><th className={TH}>Condition</th><th className={TH}>Trades</th><th className={TH}>Won</th><th className={TH}>Avg</th></tr></thead>
        <tbody>
          {d.conditions.map((c, i) => (
            <tr key={i}>
              <td className={TD}>{COND[c.cond] || c.cond}: <b>{c.val}</b></td>
              <td className={`${TD} font-semibold tabular-nums`}>{c.n}</td>
              <td className={`${TD} font-semibold tabular-nums ${c.win >= 0.6 ? 'text-up' : c.win < 0.45 ? 'text-down' : ''}`}>{pct(c.win)}</td>
              <td className={`${TD} font-semibold tabular-nums ${TONE[toneOf(c.avg_r)]}`}>{rtext(c.avg_r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {d.live.length > 0 && (<><Sub>Live demo trades</Sub><ul className="list-none text-[12.5px] leading-[1.5]">{d.live.slice(0, 8).map(row)}</ul></>)}
      <details className="mt-2">
        <summary className="cursor-pointer text-[11.5px] text-muted">Latest backtest trades ({d.n_backtest})</summary>
        <ul className="mt-1.5 list-none text-[12.5px] leading-[1.5]">{d.recent_backtest.map(row)}</ul>
      </details>
      <Meta cls="mt-1.5">Updated {new Date(d.made_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · after every analysis</Meta>
    </Card>
  )
}

