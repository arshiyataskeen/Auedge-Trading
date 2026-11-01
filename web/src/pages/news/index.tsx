import { useEffect, useState } from 'react'
import { useNews } from '../../api/endpoints'
import type { NewsEvent } from '../../api/types'
import PageHeader from '../../components/PageHeader'
import QueryCard from '../../components/QueryCard'
import { countdown } from '../../lib/time'

const TICK_MS = 30_000 // old page re-rendered every 30 s
const hhmm = (s: number) => new Date(s * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
const dayLabel = (s: number) => new Date(s * 1000).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' })

/** Current time in epoch seconds, re-read every 30 s so countdowns and the banner keep moving. */
function useNowSec(): number {
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), TICK_MS)
    return () => clearInterval(id)
  }, [])
  return now
}

const inWindow = (e: NewsEvent, now: number) => e.blocks && e.win_from <= now && now <= e.win_to

function Banner({ events, blocking, now }: { events: NewsEvent[]; blocking: NewsEvent | null; now: number }) {
  const live = events.find((e) => inWindow(e, now)) ?? (blocking && inWindow(blocking, now) ? blocking : undefined)
  const next = events.find((e) => e.blocks && e.t > now)
  return (
    <section className="mb-3 rounded border border-line bg-panel p-3">
      {live ? (
        <div data-testid="news-banner" className="flex items-center gap-2.5 rounded bg-down-bg px-3 py-2.5 text-[13px] font-semibold text-down">
          ⛔ No new trades now: {live.name} (window until {hhmm(live.win_to)})
        </div>
      ) : (
        <div data-testid="news-banner" className="flex items-center gap-2.5 rounded bg-up-bg px-3 py-2.5 text-[13px] font-semibold text-up">
          ✓ No news window now: trading allowed{next ? ` · next: ${next.name} ${countdown(next.t - now)}` : ''}
        </div>
      )}
      <p className="mt-2 text-[12px] text-muted">
        Gold moves most on US data. <b className="text-down">High</b> impact = no new trades from 30 min before to 30 min after
        (60 after a Fed decision). <b className="text-warn">Medium</b> = be careful, wider spreads possible. Times in your local time.
      </p>
    </section>
  )
}

function Row({ e, now }: { e: NewsEvent; now: number }) {
  const state = inWindow(e, now) ? 'live' : e.t < now ? 'past' : ''
  const fc = [e.forecast && `forecast ${e.forecast}`, e.previous && `previous ${e.previous}`].filter(Boolean).join(' · ')
  const chip = e.impact === 'High' ? 'bg-down-bg text-down' : e.impact === 'Medium' ? 'bg-warn-bg text-warn' : 'bg-panel2 text-muted'
  return (
    <div data-testid="news-row" data-state={state}
      className={`grid grid-cols-[52px_62px_minmax(0,1fr)_auto] items-center gap-2 border-t border-line py-[7px] text-[13px] ${state === 'past' ? 'opacity-45' : ''} ${state === 'live' ? 'bg-down-bg' : ''}`}>
      <span className="font-semibold tabular-nums">{hhmm(e.t)}</span>
      <span className={`rounded-[3px] px-1.5 py-px text-center text-[10.5px] font-bold ${chip}`}>{e.impact.toUpperCase()}</span>
      <span className="min-w-0">
        <b className="font-semibold">{e.name}</b>
        {e.blocks && <span className="ml-1.5 inline-block rounded-[3px] border border-down px-1 text-[10px] text-down">no-trade window</span>}
        <div className="text-[11.5px] text-muted">{fc || e.source}</div>
      </span>
      <span className="whitespace-nowrap text-right text-[11.5px] tabular-nums text-muted">{countdown(e.t - now)}</span>
    </div>
  )
}

/** Port of the old News tab: no-trade banner, then events grouped by local day. */
export default function NewsPage() {
  const q = useNews()
  const now = useNowSec()
  return (
    <div>
      <PageHeader title="News" subtitle="US events that move gold" />
      <QueryCard query={q} title="News">
        {(d) => {
          let day = ''
          return (
            <>
              <Banner events={d.events} blocking={d.blocking} now={now} />
              <section className="rounded border border-line bg-panel p-3">
                <h3 className="text-[12px] font-semibold text-strong">This week and coming up</h3>
                {d.events.map((e, i) => {
                  const dk = dayLabel(e.t)
                  const head = dk !== day
                  day = dk
                  return (
                    <div key={`${e.t}-${e.name}-${i}`}>
                      {head && <div data-testid="news-day" className="mb-1 mt-3 text-[11px] font-semibold uppercase tracking-[.06em] text-muted">{dk}</div>}
                      <Row e={e} now={now} />
                    </div>
                  )
                })}
                {!d.events.length && <div className="mt-2 text-[12px] text-muted">No high or medium impact US events found.</div>}
                <div className="mt-2 text-[12px] text-muted">
                  Sources: ForexFactory weekly calendar (this week), BLS and Federal Reserve official schedules (later dates).
                </div>
              </section>
            </>
          )
        }}
      </QueryCard>
    </div>
  )
}
