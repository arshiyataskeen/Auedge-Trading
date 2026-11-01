import type { RRStats } from '../../api/types'
import { money, toneOf } from '../../lib/format'
import { Alert, Card, Meta, Sect, Stat } from './ui'

const rr = (v: number | null | undefined, pre = '', suf = '') => (v == null ? '—' : `${pre}${v}${suf}`)

/** Port of rrCard: planned vs achieved risk:reward for the selected phase. */
export default function RiskReward({ rr: r }: { rr: RRStats }) {
  const dist = r.dist ?? []
  const maxN = Math.max(1, ...dist.map((d) => d.n))
  const edge = r.win_rate != null && r.breakeven_win_rate != null ? r.win_rate - r.breakeven_win_rate : null
  return (
    <Card>
      <Sect>Risk : Reward · this phase</Sect>
      {r.n_with_stop ? (
        <>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2">
            <Stat v={r.avg_planned != null ? `1 : ${r.avg_planned}` : '—'} k="average planned R:R" />
            <Stat v={r.avg_achieved != null ? `${r.avg_achieved > 0 ? '+' : ''}${r.avg_achieved}R` : '—'} k="average result per trade" tone={toneOf(r.avg_achieved)} />
            <Stat v={r.avg_win_r != null ? `+${r.avg_win_r}R` : '—'} k="average win" tone="up" />
            <Stat v={rr(r.avg_loss_r, '', 'R')} k="average loss" tone="dn" />
          </div>
          <div className="mt-1.5 grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2">
            <Stat v={rr(r.win_rate, '', '%')} k="your win rate" />
            <Stat v={rr(r.breakeven_win_rate, '', '%')} k="win rate needed to break even" />
            <Stat v={money(r.expectancy_usd)} k="expectancy per trade" tone={toneOf(r.expectancy_usd)} />
            <Stat v={r.with_target ? `${r.hit_target}/${r.with_target}` : '—'} k="reached the target" />
          </div>
          {edge != null && (
            <div className="mt-2">
              <Alert tone={edge >= 0 ? 'up' : 'down'}>
                {edge >= 0
                  ? `Your win rate is ${edge} points above what your average R:R needs. That's a real edge if it holds over more trades.`
                  : `Your win rate is ${-edge} points below what your average R:R needs. Aim for bigger targets or better entries.`}
              </Alert>
            </div>
          )}
          <h3 className="mb-1 mt-3 text-[12px] font-semibold text-strong">Results in R (1R = what you lose at the stop)</h3>
          {dist.map((d) => (
            <div key={d.label} className="flex items-center gap-2 py-0.5 text-[12px]">
              <span className="w-[110px] shrink-0 text-muted">{d.label}</span>
              <span className="h-2 flex-1 overflow-hidden rounded bg-panel2">
                <i className={`block h-full ${/−/.test(d.label) ? 'bg-down' : 'bg-up'}`} style={{ width: `${Math.round((100 * d.n) / maxN)}%` }} />
              </span>
              <b className="w-8 text-right tabular-nums">{d.n}</b>
            </div>
          ))}
          {r.n_without_stop ? <Meta cls="mt-1.5">{r.n_without_stop} trade(s) have no stop or lots recorded, so they can't be measured in R.</Meta> : null}
        </>
      ) : <Meta>Record entry, stop, target and lots on your trades to see planned vs achieved risk:reward.</Meta>}
      <Meta cls="mt-2">Planned R:R = target distance ÷ stop distance when you entered. Achieved R = your real result ÷ the money at risk. Win rate needed = 1 ÷ (1 + R:R).</Meta>
    </Card>
  )
}
