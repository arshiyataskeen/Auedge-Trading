import { useEffect, useRef, useState } from 'react'
import type { Theme } from './theme'

type TvWindow = Window & { TradingView?: { widget: new (o: Record<string, unknown>) => unknown } }
let seq = 0
let loading: Promise<void> | null = null

/**
 * Old ensureTv: load TradingView's free embeddable chart script. The first build reuses a script that is already there; a rebuild (theme change)
 * loads tv.js again, exactly like the old setTheme did, because a second widget built on the stale script can stay blank.
 */
function loadTv(fresh: boolean): Promise<void> {
  if (!fresh && (window as TvWindow).TradingView) return Promise.resolve()
  if (!fresh && loading) return loading
  const p = new Promise<void>((resolve, reject) => {
    const sc = document.createElement('script')
    sc.src = 'https://s3.tradingview.com/tv.js'
    sc.onload = () => { if (loading === p) loading = null; resolve() }
    sc.onerror = () => { if (loading === p) loading = null; sc.remove(); reject(new Error('blocked')) }
    document.head.appendChild(sc)
  })
  loading = p
  return p
}

/** TradingView's own live chart (OANDA feed, real-time ticks, drawing tools). The widget only takes a theme when created, so it is rebuilt on a theme change. */
export default function TvChart({ theme }: { theme: Theme }) {
  const [failed, setFailed] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const built = useRef(false) // a widget was created before: the next build reloads tv.js
  useEffect(() => {
    let dead = false
    const el = root.current
    if (!el) return
    setFailed(false) // a rebuild gets a fresh chance (the script may be reachable now)
    // each build gets its own container, so a stale widget can never block the next one (the old page cleared #tv and rebuilt too)
    const host = document.createElement('div')
    host.id = `tv-widget-${++seq}`
    host.style.cssText = 'width:100%;height:100%'
    el.appendChild(host)
    loadTv(built.current).then(() => {
      built.current = true
      if (dead) return
      new (window as TvWindow).TradingView!.widget({
        container_id: host.id, autosize: true, symbol: 'OANDA:XAUUSD', interval: '15',
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Etc/UTC',
        theme, style: '1', locale: 'en', allow_symbol_change: true, withdateranges: true,
        // full toolset: drawing toolbar, timeframes, chart types, indicators, compare, date ranges, screenshot
        hide_side_toolbar: false, hide_top_toolbar: false, hide_legend: false,
        // details panel off: its symbol title links out to tradingview.com; our top bar shows price and change instead
        details: false, hotlist: false, calendar: false, save_image: true, enable_publishing: false,
        overrides: { 'mainSeriesProperties.showCountdown': true },
      })
    }).catch(() => { if (!dead) setFailed(true) })
    return () => { dead = true; host.remove() }
  }, [theme])
  return (
    <div data-testid="tv-chart" className="absolute inset-0">
      <div ref={root} className="h-full w-full" />
      {failed && (
        <div role="alert" className="absolute inset-0 grid place-items-center bg-bg p-5 text-[13px] text-warn">
          Could not load the TradingView chart (no internet, or blocked). Use "Spot + zones" instead.
        </div>
      )}
    </div>
  )
}
