import type { PhaseCheck } from '../../api/types'
import { money, toneOf } from '../../lib/format'
import { Bar, Meter, usd } from '../dashboard/Cards'
import { Alert, Card, DayBars, Meta, Sect, Stat } from './ui'

/** Port of consistencyCard: best-day share vs the firm's limit, lot-size steadiness, daily results. */
export default function Consistency({ c }: { c: PhaseCheck }) {
  const k = c.consistency
  const lim = k.limit_pct, share = k.best_day_share
  const over = !!lim && share != null && share > lim
  const spread = k.lot_spread ?? 0
  const best = k.best_day
  return (
    <Card>
      <Sect>Consistency · this phase</Sect>
      {share != null && best ? (
        <>
          <Meter label={`Best day as % of total profit${lim ? ` (your firm's limit ${lim}%)` : ''}`}
            value={<span className={over ? 'text-down' : 'text-up'}>{share}%</span>}
            bar={<div className="relative"><Bar pct={share} cls={over ? 'warnb' : 'tgt'} />
              {lim ? <div className="absolute -top-px h-[9px] w-0.5 bg-strong" style={{ left: `${Math.min(100, lim)}%` }} aria-hidden /> : null}</div>} />
          <div className="mt-2">
            {lim ? (
              <Alert tone={k.ok ? 'up' : 'down'}>
                {k.ok ? `Within the rule: your best day (${best.day}, ${money(best.pnl)}) is ${share}% of the profit.`
                  : `Breaks the rule: best day ${money(best.pnl)} on ${best.day} is ${share}% of the profit. About ${usd(k.profit_needed)} more profit (spread over other days) fixes it.`}
              </Alert>
            ) : <Meta>Best day {money(best.pnl)} on {best.day}. Add your firm's consistency % in <b>Edit account</b> to check it automatically.</Meta>}
          </div>
        </>
      ) : <Meta>Shown once this phase is in profit.</Meta>}
      <div className="mt-2.5 grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2">
        <Stat v={`${k.win_days} / ${k.loss_days}`} k="green / red days" />
        <Stat v={money(k.avg_win_day)} k="average green day" tone="up" />
        <Stat v={money(k.avg_loss_day)} k="average red day" tone="dn" />
        <Stat v={money(k.worst_day)} k="worst day" tone={toneOf(k.worst_day)} />
      </div>
      <div className="mt-1.5 grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2">
        <Stat v={k.avg_lots ?? '—'} k="average lots" />
        <Stat v={k.min_lots != null ? `${k.min_lots} – ${k.max_lots}` : '—'} k="smallest – biggest lots" />
        <Stat v={k.lot_spread != null ? `×${k.lot_spread}` : '—'} k="biggest vs average lot" tone={spread > 2 ? 'dn' : ''} />
        <Stat v={k.biggest_trade_share != null ? `${k.biggest_trade_share}%` : '—'} k="biggest trade % of profit" tone={(k.biggest_trade_share ?? 0) > 50 ? 'dn' : ''} />
      </div>
      {spread > 2 && <div className="mt-2"><Alert tone="warn">Your biggest lot is more than 2× your average. Many firms flag uneven lot sizes; keep size steady.</Alert></div>}
      {c.days.length > 0 && (
        <>
          <h3 className="mb-1 mt-3 text-[12px] font-semibold text-strong">Daily results</h3>
          <DayBars days={c.days.slice(-20).reverse()} />
        </>
      )}
      <Meta cls="mt-2">Firms use consistency rules so one lucky day can't pass a challenge or a payout. Steady lots and many small green days look best.</Meta>
    </Card>
  )
}
