import { useHealthLatest, useRunHealth } from '../../api/endpoints'
import type { BacktestStatus, HealthVariant } from '../../api/types'
import MoneyText from '../../components/MoneyText'
import QueryCard from '../../components/QueryCard'
import ProgressBar from './ProgressBar'
import { btn, card, dshort, sect } from './ui'

type Props = { status?: BacktestStatus; running: boolean }

// Verdict word and colour class (old V table).
const VERDICT: Record<string, [string, string]> = {
  survives: ['OK', 'text-up'], fails: ['FAILS', 'text-down'], helps: ['HELPS', 'text-up'], promising: ['PROMISING', 'text-muted'],
  hurts: ['HURTS', 'text-down'], mixed: ['MIXED', 'text-muted'], useful: ['USEFUL', 'text-up'], noise: ['NOISE', 'text-muted'],
}
type HP = { first_t: number; last_t: number; mid: number; step: string; lot: number }

/** Port of hcLoad / hcRender / hcProgress: is the edge real? Today's rules vs harsher costs, filters and each agent left out. */
export default function HealthCheck({ status, running }: Props) {
  const q = useHealthLatest()
  const run = useRunHealth()
  const hcRunning = running && String(status?.id ?? '').startsWith('hc_')
  const dis = running || run.isPending

  const buttons = (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <button type="button" className={btn} disabled={dis} onClick={() => run.mutate('month')}>Run health check · last month (about 7 min)</button>
      <button type="button" className={btn} disabled={dis} onClick={() => run.mutate('6m')}
        title="Hourly steps over the whole history: slower, but many more trades">6 months · hourly (slower)</button>
    </div>
  )
  const foot = (
    <>
      {buttons}
      {run.isError && <div role="alert" className="mt-2 text-[12.5px] text-warn">{(run.error as Error).message}</div>}
      {hcRunning && status && <ProgressBar status={status} label="Health check" />}
    </>
  )

  return (
    <section className={`${card} mb-3`} aria-label="Health check">
      <h2 className={sect}>Health check · is the edge real?</h2>
      <QueryCard query={q}>
        {(h) => {
          if (!('id' in h) || !h.id) {
            return (
              <>
                <p className="text-[12.5px] text-muted">
                  Compares today&apos;s rules with harsher costs, three quality filters and each agent left out,
                  and checks every result in the first and second half of the period separately.
                </p>
                {foot}
              </>
            )
          }
          const base = h.variants[0]
          const pp = h.params as unknown as HP
          const usdText = (v: number) => <MoneyText v={v} />
          const row = (v: HealthVariant) => {
            const [word, tone] = VERDICT[v.verdict] ?? [v.verdict, 'text-muted']
            return (
              <div key={v.key} className="border-t border-line py-2 first:border-t-0">
                <div className="flex items-center justify-between gap-2">
                  <b className="text-[12.5px] text-strong">{v.label}</b>
                  <span className={`text-[11px] font-bold ${tone}`}>{word}</span>
                </div>
                <div className="text-[11.5px] text-muted">
                  {v.n} trades · {v.win_rate != null ? `${v.win_rate}% won` : '—'} · <b>{usdText(v.usd)}</b>
                  {v.key !== 'base' && <> ({usdText(v.usd - base.usd)} vs today)</>}
                  {' '}· halves {usdText(v.h1_usd)} / {usdText(v.h2_usd)}
                </div>
                <div className="text-[11.5px] text-muted">{v.note}</div>
              </div>
            )
          }
          const sec = (title: string, groups: string[]) => {
            const rs = h.variants.filter((v) => groups.includes(v.group))
            return rs.length ? <div key={title}><div className="mt-3 text-[11px] font-semibold uppercase text-muted">{title}</div>{rs.map(row)}</div> : null
          }
          const agents = h.variants.filter((v) => v.group === 'agent')
          const names = (verdict: string) => agents.filter((v) => v.verdict === verdict).map((v) => v.label.replace('Without ', ''))
          const useful = names('useful'), hurts = names('hurts'), noise = names('noise')
          const harsh = h.variants.find((v) => v.key === 'harsh')
          const good = h.variants.filter((v) => v.group === 'filter' && v.verdict === 'helps')
          const when = new Date(h.made_at * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
          return (
            <>
              <div className="mb-2 text-[11.5px] text-muted">
                {dshort(pp.first_t)} – {dshort(pp.last_t)} · {pp.step} steps · {pp.lot} lot · first half until {dshort(pp.mid)} · run {when}
              </div>
              <ul className="list-disc space-y-1 pl-5 text-[12.5px] text-text">
                <li><b>Today&apos;s rules:</b> {usdText(base.usd)} on {base.n} trades ({usdText(base.h1_usd)} in the first half, {usdText(base.h2_usd)} in the second). {base.note}</li>
                {harsh && (
                  <li><b>Worse fills:</b>{' '}
                    {harsh.usd > 0 ? <>still {usdText(harsh.usd)}. The edge survives realistic costs.</>
                      : <>{usdText(harsh.usd)}. The edge does not survive worse fills; don&apos;t trade it live yet.</>}
                  </li>
                )}
                <li><b>Agents:</b>{' '}
                  {useful.length ? `clearly helping: ${useful.join(', ')}. ` : 'none clearly helps. '}
                  {hurts.length ? `Hurting: ${hurts.join(', ')}. ` : ''}
                  {noise.length ? `No clear effect: ${noise.join(', ')}.` : ''}
                </li>
                <li><b>Quality filters:</b>{' '}
                  {good.length ? `${good.map((v) => v.label).join('; ')} helped in both halves. Re-check on 6 months before switching it on.`
                    : 'none helped in both halves, so keep the current rules.'}
                </li>
                {base.n < 30 && <li><b>Caution:</b> only {base.n} trades. Small samples swing a lot; the 6-month check gives more trades.</li>}
              </ul>
              <div className="mt-2">
                {sec("Today's rules", ['base', 'rules'])}
                {sec('Cost stress test', ['costs'])}
                {sec('Quality filters (only trade when…)', ['filter'])}
                {sec('Leave one agent out', ['agent'])}
              </div>
              <p className="mt-2 text-[11.5px] text-muted">
                A change only counts when it is better (or worse) by more than $25 in <b>both</b> halves; anything else could be luck.
                &quot;Useful&quot; agent = results get worse without it. Past results do not guarantee future results.
              </p>
              {foot}
            </>
          )
        }}
      </QueryCard>
    </section>
  )
}
