import { useEffect, useRef } from 'react'
import { createChart, CrosshairMode } from 'lightweight-charts'
import type { IChartApi, IPriceLine, ISeriesApi, LineStyle, SeriesMarker, UTCTimestamp } from 'lightweight-charts'
import type { BtTrade } from '../../api/types'
import { callBar, tzShift, type Bar, type CallMarker, type LevelLine } from './logic'
import type { Theme } from './theme'

const cssVar = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim()
const colors = () => ({
  layout: { background: { color: cssVar('--bg') || '#131722' }, textColor: cssVar('--chart-text') || '#b2b5be' },
  grid: { vertLines: { color: cssVar('--chart-grid') || 'rgba(42,46,57,.6)' }, horzLines: { color: cssVar('--chart-grid') || 'rgba(42,46,57,.6)' } },
  rightPriceScale: { borderColor: cssVar('--line') || '#2a2e39' }, timeScale: { borderColor: cssVar('--line') || '#2a2e39' },
})

type Props = {
  kind: 'spot' | 'fut'
  bars: Bar[]
  /** Futures carry real volume; spot candles have none. */
  volume: boolean
  /** Changing it re-fits the chart (source or timeframe switched); a plain data update keeps the user's zoom. */
  resetKey: string
  theme: Theme
  levels: LevelLine[]
  markers: CallMarker[]
  /** Price line under the newest candle showing the time left (old cdLine). */
  countdown: { price: number; title: string } | null
  /** Calls drawn as markers; a click near one opens its replay. */
  calls: BtTrade[] | null
  sec: number
  onPickCall: (t: BtTrade) => void
}

/** Old chart + draw + drawLevels + applyCallMarkers + cdLine: candles from XAUS (Spot or COMEX Futures) with the Chief's levels, call markers and a candle countdown. */
export default function SpotChart({ kind, bars, volume, resetKey, theme, levels, markers, countdown, calls, sec, onPickCall }: Props) {
  const holder = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candles = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const vol = useRef<ISeriesApi<'Histogram'> | null>(null)
  const lines = useRef<IPriceLine[]>([])
  const cd = useRef<IPriceLine | null>(null)
  const fitted = useRef('')
  const pick = useRef({ calls, sec, onPickCall })
  pick.current = { calls, sec, onPickCall }

  useEffect(() => {
    const el = holder.current
    if (!el) return
    const chart = createChart(el, {
      autoSize: true, ...colors(),
      layout: { ...colors().layout, fontFamily: '-apple-system, BlinkMacSystemFont, Trebuchet MS, Roboto, Ubuntu, sans-serif' },
      timeScale: { ...colors().timeScale, timeVisible: true, secondsVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
    })
    const series = chart.addCandlestickSeries({ upColor: '#089981', downColor: '#f23645', borderVisible: false, wickUpColor: '#089981', wickDownColor: '#f23645' })
    const hist = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'vol', color: 'rgba(41,98,255,.3)' })
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    chart.subscribeClick((p) => {
      const { calls: cl, sec: s, onPickCall: open } = pick.current
      if (!cl?.length || !p.point) return
      // Candles can be under a pixel wide, so pick the nearest arrow/circle within ~14 px of the click; horizontal distance matters most.
      let best: BtTrade | null = null, bestD = 14
      for (const t of cl) {
        for (const [ts, price] of [[t.entry_t, t.entry], [t.exit_t ? t.exit_t - 1 : null, t.exit]] as const) {
          if (!ts || price == null) continue
          const x = chart.timeScale().timeToCoordinate(callBar(ts, s) as UTCTimestamp), y = series.priceToCoordinate(price)
          if (x == null || y == null) continue
          const d = Math.hypot(x - p.point.x, (y - p.point.y) * 0.35)
          if (d < bestD) { best = t; bestD = d }
        }
      }
      if (best) open(best)
    })
    chartRef.current = chart; candles.current = series; vol.current = hist
    return () => { chartRef.current = null; candles.current = null; vol.current = null; lines.current = []; cd.current = null; fitted.current = ''; chart.remove() }
  }, [])

  useEffect(() => { chartRef.current?.applyOptions(colors()) }, [theme])

  useEffect(() => {
    const shift = tzShift()
    candles.current?.setData(bars.map((b) => ({ time: (b.time + shift) as UTCTimestamp, open: b.open, high: b.high, low: b.low, close: b.close })))
    vol.current?.setData(volume
      ? bars.map((b) => ({ time: (b.time + shift) as UTCTimestamp, value: b.volume, color: b.close >= b.open ? 'rgba(38,166,154,.35)' : 'rgba(239,83,80,.35)' }))
      : [])
    if (bars.length && fitted.current !== resetKey) { chartRef.current?.timeScale().fitContent(); fitted.current = resetKey }
  }, [bars, volume, resetKey])

  useEffect(() => {
    const s = candles.current
    if (!s) return
    lines.current.forEach((l) => s.removePriceLine(l))
    lines.current = levels.map((l) => s.createPriceLine({ price: l.price, color: l.color, lineStyle: l.style as LineStyle, lineWidth: l.width as 1 | 2, axisLabelVisible: true, title: l.title }))
  }, [levels])

  useEffect(() => { candles.current?.setMarkers(markers as SeriesMarker<UTCTimestamp>[]) }, [markers])

  useEffect(() => {
    const s = candles.current
    if (!s) return
    if (!countdown) { if (cd.current) { s.removePriceLine(cd.current); cd.current = null } return }
    if (!cd.current) cd.current = s.createPriceLine({ price: countdown.price, color: '#8a92a0', lineVisible: false, axisLabelVisible: true, title: countdown.title })
    else cd.current.applyOptions({ price: countdown.price, title: countdown.title })
  }, [countdown])

  return <div ref={holder} data-testid={`${kind}-chart`} className="absolute inset-0" />
}
