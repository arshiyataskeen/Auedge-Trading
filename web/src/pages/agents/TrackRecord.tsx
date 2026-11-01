import type { ReactNode } from 'react'
import type { Analysis, Track } from '../../api/types'
import { price, rtext } from '../../lib/format'
import { Bias } from '../dashboard/Cards'
import { Card, Meta, Sect, Stat } from '../journal/ui'
import { ConfBar } from './AgentCard'
import SeparationCard from './SeparationCard'
import { LABELS, cls } from './logic'

const TH = 'px-1 py-1 text-left text-[10.5px] font-normal uppercase text-muted'
const TD = 'border-t border-line px-1 py-1.5 align-middle'
const UP = 'text-up', DN = 'text-down'

/** Old weightsTable(): default weight, performance multiplier, weight in use, and hit rate of every voting agent. */
export function WeightsTable({ d }: { d: Analysis }) {
  const on = d.perf_weights_on
  const rows = d.agents.filter((a) => a.base_weight).map((a) => {
    const p = a.perf, m = p && p.n >= 100 ? p.mult : 1
    return { a, m, right: p ? `${p.hit_rate}% of ${p.n}` : 'no calls yet' }
  })
  const tone = (m: number) => (m > 1 ? UP : m < 1 ? DN : '')
  return (
    <Card label="Agent vote weights">
      <Sect>Agent vote weights · performance weights {on ? 'ON' : 'OFF (shown only)'}</Sect>
      {!on && (
        <Meta cls="mb-1.5">
          The Chief uses the fixed default weights. The ×multiplier shows what performance weighting would do; turn it on with USE_PERFORMANCE_WEIGHTS=1 in .env if it proves useful.
        </Meta>
      )}
      {/* under 640 px: one stacked card per agent */}
      <div className="sm:hidden">
        {rows.map(({ a, m, right }) => (
          <div key={a.agent} data-testid="weight-card" className="border-t border-line py-2 text-[12.5px]">
            <div className="flex items-center justify-between gap-2">
              <b className="text-strong">{a.label}</b><b className={`tabular-nums ${tone(m)}`}>×{m.toFixed(2)}</b>
            </div>
            <ConfBar pct={Math.round((m - 0.5) * 100)} kind={m >= 1 ? 'BUY' : 'SELL'} />
            <div className="mt-1 text-[11.5px] tabular-nums text-muted">Default {a.base_weight} · used {a.weight} · if on {a.perf_weight} · right (60 days): {right}</div>
          </div>
        ))}
      </div>
      <table className="hidden w-full border-collapse text-[12.5px] sm:table">
        <thead>
          <tr><th className={TH}>Agent</th><th className={`${TH} text-right`}>Default</th><th className={TH}><span className="sr-only">Multiplier bar</span></th>
            <th className={TH}>×</th><th className={TH}>Used</th><th className={`${TH} text-right`}>If on</th><th className={`${TH} text-right`}>Right (60 days)</th></tr>
        </thead>
        <tbody>
          {rows.map(({ a, m, right }) => (
            <tr key={a.agent}>
              <td className={TD}><b>{a.label}</b></td>
              <td className={`${TD} text-right tabular-nums text-muted`}>{a.base_weight}</td>
              <td className={TD} style={{ width: '28%' }}><ConfBar pct={Math.round((m - 0.5) * 100)} kind={m >= 1 ? 'BUY' : 'SELL'} /></td>
              <td className={`${TD} font-semibold tabular-nums ${tone(m)}`}>×{m.toFixed(2)}</td>
              <td className={`${TD} font-semibold tabular-nums`}>{a.weight}</td>
              <td className={`${TD} text-right tabular-nums text-muted`}>{a.perf_weight}</td>
              <td className={`${TD} text-right tabular-nums text-muted`}>{right}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Meta cls="mt-1.5">
        Updated every Sunday 18:00 New York from the last 60 days of scored calls (one per agent per 4 hours). Needs 100 calls before an agent's weight moves; hit rates are
        pulled toward 50% so luck barely counts; limits ×0.5 to ×1.5.
      </Meta>
    </Card>
  )
}

function Stats({ t }: { t: Track['trades'] }) {
  return (
    <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
      <Stat v={t.won} k="won" tone="up" />
      <Stat v={t.lost} k="lost" tone="dn" />
      <Stat v={t.win_rate != null ? `${t.win_rate}%` : '—'} k="win rate" />
      <Stat v={t.avg_r != null ? (t.avg_r > 0 ? '+' : '') + t.avg_r + 'R' : '—'} k="average result" />
    </div>
  )
}

const dt = (ts: number) => new Date(ts * 1000).toLocaleString()

/** Old #tab-track: weights table + the Chief's live trades + each agent's 4-hour direction record. */
export default function TrackRecord({ d }: { d: Analysis }) {
  const tr = d.track
  const T = tr?.trades
  return (
    <div className="flex flex-col gap-3">
      <WeightsTable d={d} />
      {!tr || !T ? <Card><Meta>Track record unavailable.</Meta></Card> : (
        <>
          <Card label="Chief trades">
            <Sect>Chief's "BUY / SELL NOW" trades (live, since the app first ran)</Sect>
            <Stats t={T} />
            <Meta cls="mt-1.5">{T.open} open · {T.expired} expired after 24h. Won = target 1 reached before the stop.</Meta>
            {T.recent.length > 0 && (
              <>
                <div className="mt-1.5 sm:hidden">
                  {T.recent.map((x) => (
                    <div key={x.ts} data-testid="track-card" className="flex flex-wrap items-center gap-x-2 border-t border-line py-2 text-[12.5px]">
                      <Bias kind={cls(x.side)}>{x.side}</Bias><b className="tabular-nums">{price(x.entry)}</b><span>{x.status}</span>
                      <b className="ml-auto tabular-nums">{x.result_r != null ? rtext(x.result_r) : ''}</b>
                      <span className="w-full text-[11.5px] tabular-nums text-muted">{dt(x.ts)}</span>
                    </div>
                  ))}
                </div>
                <table className="mt-1.5 hidden w-full border-collapse text-[12.5px] sm:table">
                  <tbody>
                    {T.recent.map((x) => (
                      <tr key={x.ts}>
                        <td className={`${TD} tabular-nums`}>{dt(x.ts)}</td>
                        <td className={TD}><Bias kind={cls(x.side)}>{x.side}</Bias></td>
                        <td className={`${TD} font-semibold tabular-nums`}>{price(x.entry)}</td>
                        <td className={TD}>{x.status}</td>
                        <td className={`${TD} text-right tabular-nums text-muted`}>{x.result_r != null ? rtext(x.result_r) : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </Card>
          <Card label="Agent hit rates">
            <Sect>Agents: direction right after 4 hours?</Sect>
            {Object.keys(tr.agents).length === 0 ? <Meta>Nothing scored yet.</Meta> : (
              <div>
                {Object.entries(tr.agents).map(([k, a]) => {
                  const bar: ReactNode = <ConfBar pct={a.hit_rate ?? 0} kind={(a.hit_rate ?? 0) >= 50 ? 'BUY' : 'SELL'} />
                  return (
                    <div key={k} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-0.5 border-t border-line py-1.5 text-[12.5px] sm:grid-cols-[minmax(110px,1fr)_40%_52px_auto]">
                      <b className="min-w-0">{LABELS[k] || (k === 'chief' ? 'Chief direction' : k)}</b>
                      <b className="text-right tabular-nums sm:order-3 sm:text-left">{a.hit_rate != null ? `${a.hit_rate}%` : '—'}</b>
                      <div className="col-span-2 sm:order-2 sm:col-span-1">{bar}</div>
                      <span className="col-span-2 text-[11.5px] tabular-nums text-muted sm:order-4 sm:col-span-1 sm:text-right">
                        {a.hits} right · {a.misses} wrong · {a.pending} waiting
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
            <Meta cls="mt-1.5">
              Right = price moved at least $3 their way 4 hours later. About 50% is a coin flip. Calls repeat every 15 minutes, so they are not independent. Past results do not guarantee future results.
            </Meta>
          </Card>
        </>
      )}
      <SeparationCard />
    </div>
  )
}
