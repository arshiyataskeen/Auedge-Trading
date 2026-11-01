import { useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { createChart, CrosshairMode, LineStyle } from 'lightweight-charts'
import type { SeriesMarker, UTCTimestamp } from 'lightweight-charts'
import { useCandles } from '../api/endpoints'
import type { BtTrade, Candles } from '../api/types'
import { money, price, rtext } from '../lib/format'

export const SPEEDS = [
  { label: 'Slow', ms: 800 },
  { label: 'Normal', ms: 400 },
  { label: 'Fast', ms: 150 },
] as const

const tzShift = () => -new Date().getTimezoneOffset() * 60 // chart library shows UTC, so shift to local
const when = (ts: number) =>
  new Date(ts * 1000).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
const cssVar = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim()

type Props = { trade: BtTrade; src?: string; lot?: number; onClose: () => void }

/** Port of the old openTrade + rp*: modal with the trade's levels and a candle-by-candle replay. */
export default function TradeReplay({ trade, src, lot = 0.1, onClose }: Props) {
  const t = useMemo(() => {
    const entry_t = Math.floor(trade.entry_t)
    return { ...trade, entry_t, decided_t: Math.floor(trade.decided_t || entry_t), exit_t: Math.floor(trade.exit_t || Date.now() / 1000) }
  }, [trade])
  const s = t.side === 'BUY' ? 1 : -1
  const risk = Math.abs(t.entry - t.stop)
  const be = t.entry + s * risk
  const gap = t.gap || 0
  const d$ = (x: number) => `$${Math.round(Math.abs(x) * 100 * lot).toLocaleString('en-US')}`
  const tone = t.r > 0 ? 'text-up' : t.r < 0 ? 'text-down' : ''

  const from = Math.min(t.decided_t, t.entry_t) - 6 * 3600
  const to = t.exit_t + 2 * 3600
  const q = useCandles(from, to, src)

  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    return () => prev?.focus?.()
  }, [])

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'Escape') { e.stopPropagation(); onClose(); return }
    if (e.key !== 'Tab') return
    const f = [...(dialogRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input, select, [href], [tabindex]:not([tabindex="-1"])') ?? [])]
    if (!f.length) return
    const first = f[0], last = f[f.length - 1], a = document.activeElement
    if (e.shiftKey && (a === first || !dialogRef.current?.contains(a))) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && (a === last || !dialogRef.current?.contains(a))) { e.preventDefault(); first.focus() }
  }

  let body
  if (q.isError) body = <Message text={(q.error as Error).message} />
  else if (q.data === undefined) body = <div className="p-3 text-[12px] text-muted">Loading candles…</div>
  else if (q.data.error || !Array.isArray(q.data.candles)) body = <Message text={q.data.error || 'Could not load candles for this trade.'} />
  else if (!q.data.candles.length) body = <Message text="No candles for this trade." />
  else body = <ReplayPane res={q.data} t={t} gap={gap} s={s} be={be} />

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Trade replay" onKeyDown={onKeyDown}
        className="relative max-h-[94vh] w-[min(720px,94vw)] overflow-y-auto rounded-md border border-line2 bg-panel2 p-4 text-text">
        <button ref={closeRef} type="button" aria-label="Close replay" onClick={onClose}
          className="absolute right-2 top-2 h-8 w-8 rounded text-[18px] text-muted hover:bg-hover">×</button>
        <h2 className="flex flex-wrap items-center gap-2 pr-9 text-[16px] font-bold text-strong">
          <span className={t.side === 'BUY' ? 'text-up' : 'text-down'}>{t.side}{t.kind === 'now' ? ' NOW' : ''}</span>
          Trade replay
          {t.open
            ? <span className={tone}>open{t.usd != null ? ` · ${money(t.usd)}` : ''} now</span>
            : <span className={tone}>{rtext(t.r)}{t.usd != null ? ` · ${money(t.usd)}` : ''}</span>}
        </h2>
        <p className="text-[12px] text-muted">{t.why}</p>
        <div className="my-2.5 grid grid-cols-2 gap-1.5 sm:grid-cols-3">
          <Level k="Entry" v={price(t.entry)} sub={when(t.entry_t)} cls="text-[#5b8cff]" />
          <Level k="Stop loss" v={price(t.stop)} sub={`risk ${price(risk)} = ${d$(risk)}`} cls="text-down" />
          <Level k="Half off · 1R" v={price(be)} sub="then stop to entry" cls="text-up" />
          <Level k="Target" v={price(t.t1)} sub={`${price(Math.abs(t.t1 - t.entry))} = ${d$(t.t1 - t.entry)}`} cls="text-up" />
          {t.open
            ? <Level k="Exit" v="still open" sub={`closes at stop, target or ${when(t.entry_t + 86400)}`} />
            : <Level k="Exit" v={price(t.exit)} sub={when(t.exit_t)} cls={tone} />}
          <Level k={t.open ? 'Open for' : 'Held'} v={held(t.exit_t - t.entry_t)} sub={`decided ${when(t.decided_t)}`} />
        </div>
        {body}
        <p className="mt-1.5 text-[11px] text-muted">
          {gap ? `Gold futures candles shifted to spot (−$${gap.toFixed(2)}, the gap when the trade opened), so the levels match the Demo account.`
            : src === 'backup' ? 'Spot gold 15-minute candles from your trading_research backup (the data this backtest used).'
              : 'Gold futures candles (the ones the backtest used).'}{' '}
          Blue = entry, red = stop, dotted green = half off at 1R, green = target. Press Play to replay from the entry candle; drag the slider to jump.
        </p>
      </div>
    </div>
  )
}

function held(sec: number) {
  const m = Math.max(1, Math.round(sec / 60))
  return m < 60 ? `${m} min` : `${Math.round(m / 6) / 10} h`
}

function Message({ text }: { text: string }) {
  return <div role="alert" className="rounded border border-line bg-bg p-3 text-[12px] text-warn">{text}</div>
}

function Level({ k, v, sub, cls = '' }: { k: string; v: string; sub: string; cls?: string }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-app px-[9px] py-[7px]">
      <span className="block text-[11px] text-muted">{k}</span>
      <b className={`block text-[15px] tabular-nums ${cls}`}>{v}</b>
      <i className="block truncate text-[11px] not-italic text-muted">{sub}</i>
    </div>
  )
}

type Bar = { time: UTCTimestamp; open: number; high: number; low: number; close: number }

function ReplayPane({ res, t, gap, s, be }: { res: Candles; t: BtTrade; gap: number; s: 1 | -1; be: number }) {
  const shift = tzShift()
  const { data, markers, start } = useMemo(() => {
    const data: Bar[] = res.candles.filter((c) => c.t % res.sec === 0) // whole candles only (no half-built live point)
      .map((c) => ({ time: (c.t + shift) as UTCTimestamp, open: c.o - gap, high: c.h - gap, low: c.l - gap, close: c.c - gap }))
    const bar = (ts: number) => (Math.floor(ts / res.sec) * res.sec + shift) as UTCTimestamp
    const inM: SeriesMarker<UTCTimestamp> = {
      time: bar(t.entry_t), position: s > 0 ? 'belowBar' : 'aboveBar', color: '#4c8dff',
      shape: s > 0 ? 'arrowUp' : 'arrowDown', text: `IN ${price(t.entry)}`,
    }
    const outM: SeriesMarker<UTCTimestamp>[] = t.open ? [] : [{
      time: bar(t.exit_t - 1), position: s > 0 ? 'aboveBar' : 'belowBar', color: t.r > 0 ? '#089981' : '#f23645',
      shape: 'circle', text: `OUT ${price(t.exit)}`,
    }]
    const markers = [inM, ...outM].sort((a, b) => a.time - b.time)
    const start = Math.max(1, data.findIndex((c) => c.time >= bar(t.entry_t)) + 1)
    return { data, markers, start }
  }, [res, t, gap, s, shift])

  const n = data.length
  const [i, setI] = useState(n) // show the whole trade first; Play replays from the entry candle
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<number>(400)
  const holder = useRef<HTMLDivElement>(null)
  const seriesRef = useRef<ReturnType<ReturnType<typeof createChart>['addCandlestickSeries']> | null>(null)

  // chart lifecycle
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
    const series = chart.addCandlestickSeries({ upColor: '#089981', downColor: '#f23645', borderVisible: false, wickUpColor: '#089981', wickDownColor: '#f23645' })
    const pl = (p: number, color: string, title: string, lineStyle: LineStyle = LineStyle.Solid) =>
      series.createPriceLine({ price: p, color, lineWidth: 2, lineStyle, axisLabelVisible: true, title })
    pl(t.entry, '#4c8dff', 'ENTRY'); pl(t.stop, '#f23645', 'STOP'); pl(be, '#089981', 'HALF @1R', LineStyle.Dotted); pl(t.t1, '#089981', 'TARGET')
    chart.timeScale().setVisibleLogicalRange({ from: -1, to: n + 1 })
    seriesRef.current = series
    setI((v) => Math.min(Math.max(1, v), n))
    return () => { seriesRef.current = null; chart.remove() }
  }, [n, t, be])

  // draw candles up to i
  useEffect(() => {
    const series = seriesRef.current
    if (!series || !n) return
    const k = Math.max(1, Math.min(n, i))
    series.setData(data.slice(0, k))
    const last = data[k - 1].time
    series.setMarkers(markers.filter((m) => m.time <= last))
  }, [i, data, markers, n])

  // play timer
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
    if (i >= n) setI(start)
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
