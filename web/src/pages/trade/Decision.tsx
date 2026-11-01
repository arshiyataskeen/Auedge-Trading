import type { KeyboardEvent } from 'react'
import type { Analysis } from '../../api/types'
import { price } from '../../lib/format'
import { Bias } from '../dashboard/Cards'
import { MOOD_CLS, cls } from '../agents/logic'
import { readStored, sizeInfo, useStored } from './logic'
import { useMyDay } from './Psych'

/** Old sizeText(): "Size for $1,000 at 1% risk: 0.83 oz ≈ 0.01 lots (lose about $10 if the stop is hit)". */
export function SizeLine({ plan }: { plan: Analysis['chief']['plan'] }) {
  const [acct] = useStored('acct', '1000'), [risk] = useStored('riskPct', '1')
  const s = sizeInfo(plan, parseFloat(acct), parseFloat(risk))
  if (!s) return null
  return <>Size for ${s.acct.toLocaleString()} at {s.riskPct}% risk: <b>{s.oz.toFixed(2)} oz ≈ {s.lots.toFixed(2)} lots</b> (lose about ${s.riskUsd.toFixed(0)} if the stop is hit)</>
}

const BORDER = { BUY: 'shadow-[inset_3px_0_0_var(--up)]', SELL: 'shadow-[inset_3px_0_0_var(--down)]', NA: 'shadow-[inset_3px_0_0_var(--warn)]', WAIT: 'shadow-[inset_3px_0_0_var(--line2)]' }
const ACTION = { BUY: 'text-up', SELL: 'text-down', NA: 'text-warn', WAIT: 'text-strong' }
const TEXT = { BUY: 'text-up', SELL: 'text-down', NA: 'text-warn', WAIT: '' }

function Lv({ k, tone = '', children, d }: { k: string; tone?: string; children: string; d: string }) {
  return (
    <div className="min-w-0 bg-bg px-2 py-[7px]">
      <div className="text-[11px] text-muted">{k}</div>
      <div className={`text-[15px] font-bold tabular-nums ${tone}`}>{children}</div>
      <div className="truncate text-[11px] tabular-nums text-muted">{d}</div>
    </div>
  )
}

/** The old #decision banner: the one thing a beginner should read first. Click, Enter or Space opens the Chief details. */
export default function Decision({ d, onOpen }: { d: Analysis; onOpen: () => void }) {
  const c = d.chief, plan = c.plan, dc = d.data_check, p = c.price
  const psy = d.agents.find((a) => a.agent === 'psychology'), crowd = d.agents.find((a) => a.agent === 'sentiment')
  const { my, myStop } = useMyDay()
  useStored('lot', '0.1') // re-render when the lot size changes elsewhere
  const disc = /^(NO TRADE \(discipline\)|WAIT \(don't chase)/.test(plan.action)
  const userStop = !dc.veto && myStop && plan.kind !== 'none'
  const tone = dc.veto || disc || userStop ? 'NA' : plan.kind === 'now' ? cls(plan.side || '') : 'WAIT'
  const action = dc.veto ? 'NO TRADE NOW' : userStop ? 'DONE FOR TODAY' : plan.action
  const why = dc.veto ? (dc.warnings[0] || dc.headline)
    : userStop ? `You logged ${my.trades} trade(s) and ${my.losses} loss(es) today: your rule says stop. (The plan was: ${plan.action}.)` : c.headline
  const mindCls = ({ CLEAR: 'BUY', CAUTION: 'NA', STOP: 'SELL' } as const)[psy?.bias_label as 'CLEAR'] || 'WAIT'
  const dist = (x: number | null) => (p == null || x == null ? '' : `${x >= p ? '+' : '−'}${price(Math.abs(x - p))} from price`)
  const news = psy?.rows?.find((r) => r[0] === 'Next big news')
  const t = c.today
  const key = (e: KeyboardEvent) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onOpen() } }

  let lv = null
  if (plan.stop != null && !userStop && plan.entry_lo != null && plan.entry_hi != null) {
    const entry = (plan.entry_lo + plan.entry_hi) / 2, risk = Math.abs(entry - plan.stop)
    const r = (x: number) => (risk ? ` · ${(Math.abs(x - entry) / risk).toFixed(1)}R` : '')
    const oz = 100 * parseFloat(readStored('lot', '0.1'))
    const usd = (x: number) => `$${Math.round(Math.abs(x - entry) * oz).toLocaleString()}`
    lv = (
      <div className="mt-2.5 grid grid-cols-2 gap-px overflow-hidden rounded bg-line sm:grid-cols-4 min-[900px]:max-[1499px]:grid-cols-2">
        <Lv k="Entry" tone="text-[#5b8cff]" d={`${price(plan.entry_lo)} – ${price(plan.entry_hi)}`}>{price(entry)}</Lv>
        <Lv k="Stop loss" tone="text-down" d={`−${usd(plan.stop)} at ${oz / 100} lot`}>{price(plan.stop)}</Lv>
        {plan.be_at != null && <Lv k="Half off · 1R" tone="text-up" d="then stop to entry">{price(plan.be_at)}</Lv>}
        {plan.t1 != null && <Lv k="Target" tone="text-up" d={`+${usd(plan.t1)}${r(plan.t1)}`}>{price(plan.t1)}</Lv>}
      </div>
    )
  } else if (plan.kind === 'watch' && !userStop && plan.entry_lo != null && plan.entry_hi != null) {
    // WATCH: one level, plus what has to happen before it becomes a trade
    const sell = plan.side === 'SELL', wl = plan.side === 'BUY' ? plan.entry_hi : plan.entry_lo
    lv = (
      <div className="mt-2.5 grid gap-px overflow-hidden rounded bg-line sm:grid-cols-[minmax(0,1fr)_minmax(0,2.2fr)]">
        <Lv k="Watch level · alert only" tone="text-[#5b8cff]" d={dist(wl) || 'set a price alert here'}>{price(wl)}</Lv>
        <div className="bg-bg px-2 py-[7px]">
          <div className="text-[11px] text-muted">What to wait for</div>
          <div className="mt-0.5 text-[12.5px] leading-[1.4]">
            {sell ? <>Price spikes <b>above {price(wl)}</b> (buy stops get taken), then a 15m candle <b>closes back below</b> it.</>
              : <>Price dips <b>below {price(wl)}</b> (sell stops get taken), then a 15m candle <b>closes back above</b> it.</>}
          </div>
          <div className="mt-[3px] text-[11px] text-muted">Then AuEdge gives a <b>{plan.side} NOW</b> with entry, stop and target. Don't enter at the alert itself.</div>
        </div>
      </div>
    )
  }

  return (
    <div role="button" tabIndex={0} onClick={onOpen} onKeyDown={key}
      title="Click for the full plan and the position-size calculator"
      className={`cursor-pointer border-b border-line bg-bg p-3 hover:bg-rowhover focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent ${BORDER[tone]}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-[.06em] text-muted">Chief analyst decision</span>
        <span className="flex-1" />
        <Bias kind={cls(c.htf_label)}>{c.htf_label}</Bias>
        {!dc.veto && <Bias kind="WAIT">Confidence {c.confidence}%</Bias>}
      </div>
      <div className={`my-0.5 text-[22px] font-extrabold leading-tight ${ACTION[tone]}`}>{action}</div>
      <div className="text-[13px] leading-[1.4]">{why}</div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
        {news && <span title="No new trades from 30 min before to 30 min after (60 after a Fed decision)"><Bias kind="NA">News: {news[1]}</Bias></span>}
        {crowd?.status === 'OK' && <span title={crowd.summary}><Bias kind={MOOD_CLS[String(crowd.metrics.mood)] || 'WAIT'}>Crowd: {String(crowd.metrics.mood)}</Bias></span>}
        {psy?.status === 'OK' && <><Bias kind={mindCls}>Mindset: {psy.bias_label}</Bias><span>{psy.headline}</span></>}
      </div>
      {lv}
      {t?.trend && (
        <div className="mt-2 text-[12.5px]" title={t.tfs}>
          <b className={TEXT[cls(t.side || '')]}>TODAY: {t.trend}</b> · {t.text}
        </div>
      )}
      {plan.stop != null && <div className="mt-1.5 text-[12px] text-muted"><SizeLine plan={plan} /> · <u>change account size</u></div>}
    </div>
  )
}
