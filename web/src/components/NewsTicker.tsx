import { useEffect, useState } from 'react'
import { useNews } from '../api/endpoints'
import { span, upcomingHigh } from '../lib/sessions'

/** Slim scrolling strip of upcoming High-impact USD events; hidden when there are none. */
export default function NewsTicker() {
  const news = useNews()
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => { const id = setInterval(() => setNow(Date.now() / 1000), 30000); return () => clearInterval(id) }, [])
  const evs = upcomingHigh(news.data?.events, now)
  if (!evs.length) return null
  const items = evs.map((e) => (
    <span key={e.t + e.name} data-testid="ticker-item" className="mr-8 inline-flex items-center gap-2 whitespace-nowrap text-[11.5px] text-text">
      <b className="text-strong">{e.name}</b>
      <span className="text-muted">{new Date(e.t * 1000).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })}</span>
      <span className="text-muted">in {span(e.t - now)}</span>
      <span className="rounded-full bg-down-bg px-2 py-0.5 text-[9px] font-bold tracking-[.1em] text-down">HIGH IMPACT</span>
    </span>
  ))
  return (
    <div data-testid="news-ticker" aria-label="Upcoming high-impact USD events" className="ticker shrink-0 overflow-hidden border-b border-line bg-bg py-1.5">
      <div className="ticker-track flex w-max">
        <div className="flex">{items}</div>
        <div className="flex" aria-hidden="true">{items}</div>
      </div>
    </div>
  )
}
