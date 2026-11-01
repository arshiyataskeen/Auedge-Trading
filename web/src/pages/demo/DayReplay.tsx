import { useEffect, useMemo, useRef, useState } from 'react'
import { createChart, CrosshairMode } from 'lightweight-charts'
import type { SeriesMarker, UTCTimestamp } from 'lightweight-charts'
import { useCandles } from '../../api/endpoints'
import type { CalendarDayDetail, Candles } from '../../api/types'
import MoneyText from '../../components/MoneyText'
import { SPEEDS } from '../../components/TradeReplay'
import { money, price } from '../../lib/format'

const tzShift = () => -new Date().getTimezoneOffset() * 60
const cssVar = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim()
const when = (ts: number) =>
  new Date(ts * 1000).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

type Bar = { time: UTCTimestamp; open: number; high: number; low: number; close: number }

/** Port of openDayReplay: the whole day's candles with the Chief's NOW calls and the demo trades, replayable. */
export default function DayReplay({ d, onClose }: { d: CalendarDayDetail; onClose: () => void }) {
  const from = Math.floor(Math.min(d.window[0], ...d.trades.map((t) => t.entry_t - 3600)))
  const q = useCandles(from, d.window[1])
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    return () => prev?.focus?.()
  }, [])
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === 'Escape') { e.stopPropagation(); onCloseRef.current(); return }
      if (e.key !== 'Tab') return
      const dlg = dialogRef.current
      if (!dlg) return
      const f = [...dlg.querySelectorAll<HTMLElement>('button:not([disabled]), input, select, [tabindex]:not([tabindex="-1"])')]
      if (!f.length) return
      const first = f[0], last = f[f.length - 1], a = document.activeElement
      const inside = !!a && dlg.contains(a)
      if (e.shiftKey && (a === first || !inside)) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && (a === last || !inside)) { e.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  let body
  if (q.isError) body = <Message text={(q.error as Error).message} />
  else if (q.data === undefined) body = <div className="p-3 text-[12px] text-muted">Loading candles…</div>
  else if (q.data.error || !Array.isArray(q.data.candles)) body = <Message text={q.data.error || 'Could not load candles for this day.'} />
  else if (!q.data.candles.length) body = <Message text="No candles for this day." />
  else body = <Pane res={q.data} d={d} />

  const nice = new Date(d.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Day replay" tabIndex={-1}
        className="relative max-h-[94vh] w-[min(720px,94vw)] overflow-y-auto rounded-md border border-line2 bg-panel2 p-4 text-text">
        <button ref={closeRef} type="button" aria-label="Close replay" onClick={onClose}
          className="absolute right-2 top-2 h-8 w-8 rounded text-[18px] text-muted hover:bg-hover">×</button>
        <h2 className="pr-9 text-[16px] font-bold text-strong">Day replay · {nice} <b><MoneyText v={d.pnl} /></b></h2>
        <p className="mb-2 text-[12px] text-muted">{d.trades.length} demo trade(s) · ▲▼ entries, ● exits, small dots = moments the Chief said BUY / SELL NOW</p>
        {body}
      </div>
    </div>
  )
}

function Message({ text }: { text: string }) {
  return <div role="alert" className="rounded border border-line bg-bg p-3 text-[12px] text-warn">{text}</div>
}

function Pane({ res, d }: { res: Candles; d: CalendarDayDetail }) {
  const shift = tzShift()
  const { data, markers } = useMemo(() => {
    const dgap = d.trades.find((x) => x.gap)?.gap || 0 // live demo trades are in spot: show the candles in spot too
    const data: Bar[] = res.candles.filter((c) => c.t % res.sec === 0)
      .map((c) => ({ time: (c.t + shift) as UTCTimestamp, open: c.o - dgap, high: c.h - dgap, low: c.l - dgap, close: c.c - dgap }))
    const have = new Set(data.map((c) => c.time))
    const bar = (ts: number) => (Math.floor(ts / res.sec) * res.sec + shift) as UTCTimestamp
    const m: SeriesMarker<UTCTimestamp>[] = []
    for (const a of d.timeline.filter((x) => x.k === 'now')) {
      if (have.has(bar(a.t - 1))) m.push({ time: bar(a.t - 1), position: a.sd === 'BUY' ? 'belowBar' : 'aboveBar', color: '#f0b429', shape: 'circle', size: 0.6, text: 'NOW' })
    }
    for (const t of d.trades) {
      const s = t.side === 'BUY' ? 1 : -1
      if (have.has(bar(t.entry_t))) m.push({ time: bar(t.entry_t), position: s > 0 ? 'belowBar' : 'aboveBar', color: '#4c8dff', shape: s > 0 ? 'arrowUp' : 'arrowDown', text: `IN ${price(t.entry)}` })
      if (t.exit_t && !t.open && have.has(bar(t.exit_t - 1))) {
        m.push({ time: bar(t.exit_t - 1), position: s > 0 ? 'aboveBar' : 'belowBar', color: (t.usd ?? 0) >= 0 ? '#089981' : '#f23645', shape: 'circle', text: money(t.usd) })
      }
    }
    return { data, markers: m.sort((a, b) => a.time - b.time) }
  }, [res, d, shift])

  const n = data.length
  const [i, setI] = useState(n)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<number>(400)
  const holder = useRef<HTMLDivElement>(null)
  const seriesRef = useRef<ReturnType<ReturnType<typeof createChart>['addCandlestickSeries']> | null>(null)

  useEffect(() => {
    const el = holder.current
    if (!el || !n) return
    const grid = cssVar('--chart-grid'), line = cssVar('--line')
    const chart = createChart(el, {
      autoSize: true,
      layout: { background: { color: cssVar('--bg') || 'transparent' }, textColor: cssVar('--chart-text') || '#888' },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      rightPriceScale: { borderColor: line },
      timeScale: { borderColor: line, timeVisible: true, secondsVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
    })
    seriesRef.current = chart.addCandlestickSeries({ upColor: '#089981', downColor: '#f23645', borderVisible: false, wickUpColor: '#089981', wickDownColor: '#f23645' })
    chart.timeScale().setVisibleLogicalRange({ from: -1, to: n + 1 })
    setI((v) => Math.min(Math.max(1, v), n))
    return () => { seriesRef.current = null; chart.remove() }
  }, [n])

  useEffect(() => {
    const series = seriesRef.current
    if (!series || !n) return
    const k = Math.max(1, Math.min(n, i))
    series.setData(data.slice(0, k))
    const last = data[k - 1].time
    series.setMarkers(markers.filter((m) => m.time <= last))
  }, [i, data, markers, n])

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setI((v) => v + 1), speed)
    return () => clearInterval(id)
  }, [playing, speed])
  useEffect(() => { if (playing && i >= n) setPlaying(false) }, [playing, i, n])

  const k = Math.max(1, Math.min(n, i))
  const cur = data[k - 1]
  const stop = () => setPlaying(false)
  const play = () => {
    if (playing) return stop()
    if (i >= n) setI(1)
    setPlaying(true)
  }
  const btn = 'rounded bg-panel2 px-2.5 py-1 text-[13px] text-strong hover:bg-hover'
  return (
    <div>
      <div ref={holder} data-testid="rp-chart" className="h-[240px] overflow-hidden rounded-md border border-line bg-bg sm:h-[300px]" />
      <div className="mt-2 flex items-center gap-1.5">
        <button type="button" className={btn} title="One candle back" aria-label="Step back" onClick={() => { stop(); setI(k - 1 < 1 ? 1 : k - 1) }}>⏮</button>
        <button type="button" className={`${btn} min-w-[84px] !bg-accent`} onClick={play}>{playing ? '⏸ Pause' : '▶ Play'}</button>
        <button type="button" className={btn} title="One candle forward" aria-label="Step forward" onClick={() => { stop(); setI(Math.min(n, k + 1)) }}>⏭</button>
        <input type="range" min={1} max={n} value={k} aria-label="Replay position" className="min-w-[60px] flex-1 accent-accent"
          onChange={(e) => { stop(); setI(+e.target.value) }} />
        <select aria-label="Replay speed" value={speed} onChange={(e) => setSpeed(+e.target.value)}
          className="rounded border border-line2 bg-app p-1 text-text">
          {SPEEDS.map((o) => <option key={o.ms} value={o.ms}>{o.label}</option>)}
        </select>
      </div>
      <div className="mt-1.5 text-[12px] text-muted">
        <span data-testid="rp-time">{when(cur.time - shift)}</span> · price <b data-testid="rp-price" className="text-strong">{price(cur.close)}</b>
      </div>
    </div>
  )
}
