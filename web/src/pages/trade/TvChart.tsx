import { useEffect, useState } from 'react'
import type { Theme } from './theme'

type TvWindow = Window & { TradingView?: { widget: new (o: Record<string, unknown>) => unknown } }
const ID = 'tv-widget'
let loading: Promise<void> | null = null

/** Old ensureTv: load TradingView's free embeddable chart script once. */
function loadTv(): Promise<void> {
  if ((window as TvWindow).TradingView) return Promise.resolve()
  if (!loading) {
    loading = new Promise<void>((resolve, reject) => {
      const sc = document.createElement('script')
      sc.src = 'https://s3.tradingview.com/tv.js'
      sc.onload = () => resolve()
      sc.onerror = () => { loading = null; sc.remove(); reject(new Error('blocked')) }
      document.head.appendChild(sc)
    })
  }
  return loading
}

/** TradingView's own live chart (OANDA feed, real-time ticks, drawing tools). The widget only takes a theme when created, so it is rebuilt on a theme change. */
export default function TvChart({ theme }: { theme: Theme }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let dead = false
    const el = document.getElementById(ID)
    loadTv().then(() => {
      if (dead || !el) return
      el.innerHTML = ''
      new (window as TvWindow).TradingView!.widget({
        container_id: ID, autosize: true, symbol: 'OANDA:XAUUSD', interval: '15',
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Etc/UTC',
        theme, style: '1', locale: 'en', allow_symbol_change: true, withdateranges: true,
        // full toolset: drawing toolbar, timeframes, chart types, indicators, compare, date ranges, screenshot
        hide_side_toolbar: false, hide_top_toolbar: false, hide_legend: false,
        // details panel off: its symbol title links out to tradingview.com; our top bar shows price and change instead
        details: false, hotlist: false, calendar: false, save_image: true, enable_publishing: false,
        overrides: { 'mainSeriesProperties.showCountdown': true },
      })
    }).catch(() => { if (!dead) setFailed(true) })
    return () => { dead = true; if (el) el.innerHTML = '' }
  }, [theme])
  return (
    <div data-testid="tv-chart" className="absolute inset-0">
      <div id={ID} className="h-full w-full" />
      {failed && (
        <div role="alert" className="absolute inset-0 grid place-items-center bg-bg p-5 text-[13px] text-warn">
          Could not load the TradingView chart (no internet, or blocked). Use "Spot + zones" instead.
        </div>
      )}
    </div>
  )
}
