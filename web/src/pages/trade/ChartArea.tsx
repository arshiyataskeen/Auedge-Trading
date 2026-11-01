import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useCalls, useFuturesChart, useSpotSamples } from '../../api/endpoints'
import { useLivePrice } from '../../api/live'
import type { Analysis, BtTrade } from '../../api/types'
import TradeReplay from '../../components/TradeReplay'
import { money, price } from '../../lib/format'
import SpotChart from './SpotChart'
import TvChart from './TvChart'
import {
  TF, TF_NAMES, ago, aggregate, callMarkers, chartLevels, firstSpotTf, fmtLeft, futuresBars, leftSec, spotOk, spotSampleSec,
  withTick, DEFAULT_SAMPLE_SEC, type Bar, type Src, type TfName,
} from './logic'
import { useTheme } from './theme'

const fmt2 = (n: number) => price(n)
const ASSUMED_LOT = 0.1
const SRC: { key: Src; t: string; s: string; title: string }[] = [
  { key: 'tv', t: 'TradingView', s: 'Live ticks · tools', title: "TradingView's own live chart, tick by tick (OANDA XAU/USD feed). Has drawing tools and indicators." },
  { key: 'spot', t: 'Spot + zones', s: "Agents' levels", title: "Spot gold price from XAUS. The agents' entry, stop, targets and stop pools are drawn on this chart." },
  { key: 'fut', t: 'Futures', s: 'COMEX · delayed', title: 'Real OHLC candles, but these are COMEX gold futures (a few dollars above spot, delayed)' },
]
const SEG = (on: boolean) => `rounded px-2.5 py-1 text-[12px] ${on ? 'bg-acc-bg text-strong' : 'text-muted hover:bg-hover'}`

/** Old cdPill: time left before the current candle closes; the ring fills as the candle runs, amber in the last minute, red in the last 15 s. */
function CountdownPill({ tf, nowSec, title }: { tf: TfName; nowSec: number; title: string }) {
  const sec = TF[tf].sec, left = leftSec(sec, nowSec)
  const tone = left <= 15 ? 'now' : left <= 60 ? 'soon' : ''
  return (
    <span data-testid="cd-pill" title={title}
      className={`inline-flex h-8 items-center gap-1.5 rounded border border-line px-2 text-[12px] ${tone === 'now' ? 'animate-pulse text-down' : tone === 'soon' ? 'text-warn' : 'text-text'}`}>
      <svg viewBox="0 0 20 20" className="h-[18px] w-[18px] -rotate-90" aria-hidden="true">
        <circle cx="10" cy="10" r="8" fill="none" stroke="var(--hover)" strokeWidth="2.5" />
        <circle cx="10" cy="10" r="8" fill="none" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="50.27"
          stroke={tone === 'now' ? 'var(--down)' : tone === 'soon' ? 'var(--warn)' : 'var(--accent)'}
          style={{ strokeDashoffset: (50.27 * left / sec).toFixed(2) }} />
      </svg>
      <b className="rounded bg-hover px-1.5 font-bold">{tf}</b>
      <span className="text-muted max-[1450px]:hidden">closes in</span>
      <b className="tabular-nums">{fmtLeft(sec, nowSec)}</b>
    </span>
  )
}

/** Chart toolbar + chart (old header controls, #wrap, foot). */
export default function ChartArea({ analysis }: { analysis: Analysis | undefined }) {
  const theme = useTheme()
  const lp = useLivePrice()
  const [src, setSrc] = useState<Src>('tv')
  const [tf, setTf] = useState<TfName>('15m')
  const [tvTf, setTvTf] = useState<TfName>('15m')
  const [days, setDays] = useState(0) // Calls: off -> 7 -> 30 -> off
  const [zones, setZones] = useState(true)
  const [replay, setReplay] = useState<BtTrade | null>(null)
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => { const id = setInterval(() => setNow(Date.now() / 1000), 1000); return () => clearInterval(id) }, [])

  useEffect(() => { if (src === 'tv') window.dispatchEvent(new Event('resize')) }, [src]) // TradingView sized itself while hidden
  const spot = useSpotSamples(src === 'spot')
  const fut = useFuturesChart(src === 'fut', TF[tf].fut.interval, TF[tf].fut.range)
  const callsQ = useCalls(days)
  const calls = days > 0 && callsQ.data ? callsQ.data.calls : null

  const sampleSec = spot.data ? spotSampleSec(spot.data) : DEFAULT_SAMPLE_SEC
  // Spot cannot show timeframes with fewer than 3 samples per candle: fall back to the first one that can.
  const tfEff: TfName = src === 'spot' && !spotOk(tf, sampleSec) ? firstSpotTf(sampleSec) : tf
  const sec = TF[tfEff].sec

  const lpPrice = lp.price, lpAt = lp.updatedAt
  // Spot candles = the fetched samples plus every live tick since (old addSpotTick mutated state.bars): rebuilt only when the samples or the timeframe change.
  const spotBase = useMemo<Bar[]>(() => {
    const pts = (spot.data?.points ?? []).filter((p) => p.p != null)
    return pts.length ? aggregate(pts, sec) : []
  }, [spot.data, sec])
  const [spotBars, setSpotBars] = useState<Bar[]>([])
  const tickRef = useRef({ price: lpPrice, at: lpAt })
  tickRef.current = { price: lpPrice, at: lpAt }
  useEffect(() => {
    const { price: p, at } = tickRef.current
    setSpotBars(p != null && at != null ? withTick(spotBase, p, at, sec) : spotBase)
  }, [spotBase, sec])
  useEffect(() => {
    if (lpPrice != null && lpAt != null) setSpotBars((prev) => withTick(prev, lpPrice, lpAt, sec))
  }, [lpPrice, lpAt, sec])

  // A failed background poll keeps the candles already on screen (as the old code did); the message is for "nothing to show".
  const { bars, error } = useMemo<{ bars: Bar[]; error: string | null }>(() => {
    if (src === 'spot') {
      if (spot.data) return spotBars.length ? { bars: spotBars, error: null } : { bars: [], error: 'No spot samples returned' }
      return { bars: [], error: spot.isError ? (spot.error as Error).message : null }
    }
    if (src === 'fut') {
      if (fut.data) {
        const b = futuresBars(fut.data, tfEff)
        return b.length ? { bars: b, error: null } : { bars: [], error: 'No candles returned' }
      }
      return { bars: [], error: fut.isError ? (fut.error as Error).message : null }
    }
    return { bars: [], error: null }
  }, [src, spot.data, spot.isError, spot.error, spotBars, fut.data, fut.isError, fut.error, tfEff])

  const q = src === 'spot' ? spot : fut
  const msg = src === 'tv' ? '' : error
    ? `Candles unavailable right now (${error}). Nothing is shown rather than made-up candles. Retrying in 60 s.`
    : q.data === undefined ? 'Loading…' : ''

  const levels = useMemo(() => (zones && src === 'spot' && analysis ? chartLevels(analysis.chief) : []), [zones, src, analysis])
  const markers = useMemo(
    () => (calls && src !== 'tv' ? callMarkers(calls, bars.map((b) => b.time), sec, fmt2, (v) => money(v)) : []),
    [calls, src, bars, sec])

  const last = bars[bars.length - 1]
  const showCd = src !== 'tv' && !!last && sec < 86400
  const countdown = useMemo(
    () => (showCd && last ? { price: last.close, title: fmtLeft(sec, now) } : null),
    [showCd, last, sec, now])

  const setSource = (s: Src) => { if (s !== src) setSrc(s) }
  const cycleCalls = () => {
    const next = days === 0 ? 7 : days === 7 ? 30 : 0
    setDays(next)
    if (next > 0 && src === 'tv') { // TradingView's chart can't show our arrows: use the Futures candles
      setSrc('fut')
      if (!['15m', '1h'].includes(tf)) setTf('15m')
    }
  }

  let label: ReactNode = null
  if (calls && src !== 'tv') {
    label = <><b>Calls, last {days} days:</b> {calls.length} trades ({calls.filter((t) => t.source === 'demo').length} demo, {calls.filter((t) => t.source === 'backtest').length} backtest) · arrow = entry, circle = exit · click one to replay</>
  } else if (src === 'spot' && bars.length) {
    label = <><b>Spot XAU/USD</b> · candles aggregated from {sampleSec / 60}-min samples ({spot.data?.source || 'xaus sampler'}) + live price every 15 s · last 48 h only</>
  } else if (src === 'fut' && fut.data && bars.length) {
    const age = Date.now() / 1000 - (fut.data.points[fut.data.points.length - 1]?.t ?? 0)
    label = <><b>Gold FUTURES (COMEX), not spot</b> · real OHLCV via Yahoo Finance proxy{TF[tfEff].fut.aggregate ? ' · 4h built from 1h candles' : ''} · newest candle {ago(age)} (Yahoo data is delayed)</>
  }
  const gap = src === 'fut' && last && lpPrice != null ? last.close - lpPrice : null

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Chart source" className="flex gap-0.5 rounded border border-line bg-panel p-0.5">
          {SRC.map((x) => (
            <button key={x.key} type="button" aria-pressed={src === x.key} title={x.title} onClick={() => setSource(x.key)}
              className={`flex flex-col items-start px-2.5 py-0.5 text-left leading-tight ${SEG(src === x.key)}`}>
              <span className="text-[12px] font-semibold">{x.t}</span><span className="text-[10px] font-normal text-muted max-sm:hidden">{x.s}</span>
            </button>
          ))}
        </div>
        {src !== 'tv' && (
          <div role="group" aria-label="Timeframe" className="flex gap-0.5 rounded border border-line bg-panel p-0.5">
            {TF_NAMES.map((n) => {
              const ok = src === 'spot' ? spotOk(n, sampleSec) : true
              return (
                <button key={n} type="button" disabled={!ok} aria-pressed={n === tfEff} onClick={() => setTf(n)} className={`${SEG(n === tfEff)} disabled:opacity-40`}
                  title={ok ? undefined : TF[n].spot || n === '1m'
                    ? `Unavailable for spot: prices are sampled every ${sampleSec / 60} min, so ${n} candles would hold fewer than 3 prices`
                    : 'Unavailable for spot: only 48 hours of spot samples exist'}>
                  {n}
                </button>
              )
            })}
          </div>
        )}
        {src === 'tv' && (
          <label className="flex items-center gap-1 text-[11px] text-muted"
            title="TradingView's chart cannot tell this page which timeframe you picked inside it, so choose the same one here.">
            <select aria-label="TradingView timeframe" value={tvTf} onChange={(e) => setTvTf(e.target.value as TfName)}
              className="rounded border border-line bg-bg px-1 py-0.5 text-[11px] text-text">
              {TF_NAMES.filter((n) => n !== '1d').map((n) => <option key={n}>{n}</option>)}
            </select>
          </label>
        )}
        {src === 'tv' && <CountdownPill tf={tvTf} nowSec={now} title="Time left before the current candle closes. Choose the timeframe you picked inside TradingView." />}
        {showCd && <CountdownPill tf={tfEff} nowSec={now} title={`Time left before the current candle closes${src === 'fut' ? ' (futures data is delayed).' : '.'}`} />}
        <button type="button" onClick={cycleCalls} aria-pressed={days > 0}
          title="Show trade calls on the chart (demo + backtest). Click: 7 days, again: 30 days, again: hide. Click an arrow to replay that trade."
          className={`flex h-8 items-center gap-1.5 rounded border px-2.5 text-[12px] ${days ? 'border-accent bg-acc-bg text-strong' : 'border-line text-muted hover:bg-hover'}`}>
          <svg viewBox="0 0 24 24" className="h-[15px] w-[15px] fill-none stroke-current" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M7 4v13M3.5 13.5 7 17l3.5-3.5" /><path d="M17 20V7M13.5 10.5 17 7l3.5 3.5" />
          </svg>
          {days ? `Calls ${days}d` : 'Calls'}
        </button>
        {gap != null && <span className="text-[11.5px] text-muted max-[1400px]:hidden">Futures − spot: {gap >= 0 ? '+' : ''}{price(gap)} $</span>}
        <label className={`ml-auto flex items-center gap-1 text-[12px] text-muted ${src === 'tv' ? 'max-sm:hidden' : ''}`}
          title="Zones can only be drawn on the Spot chart, not inside TradingView">
          <input type="checkbox" checked={zones} onChange={(e) => setZones(e.target.checked)} className="accent-accent" /> Zones
        </label>
      </div>
      <div className="relative h-[58svh] min-h-[320px] overflow-hidden rounded border border-line bg-bg min-[900px]:h-[calc(100svh-12rem)] min-[900px]:min-h-[420px]">
        <div hidden={src !== 'tv'} aria-hidden={src !== 'tv'} className="absolute inset-0"><TvChart theme={theme} /></div>
        {src !== 'tv' && (
          <SpotChart key={src} kind={src} bars={bars} volume={src === 'fut'} resetKey={`${src}|${tfEff}`} theme={theme}
            levels={levels} markers={markers} countdown={countdown} calls={calls} sec={sec} onPickCall={setReplay} />
        )}
        {label && <div className="pointer-events-none absolute left-1.5 top-1.5 z-[3] max-w-[calc(100%-12px)] rounded border border-line bg-bg px-2 py-0.5 text-[11px] text-muted">{label}</div>}
        {msg && <div role={error ? 'alert' : 'status'} className="absolute inset-0 z-[4] flex items-center justify-center p-6 text-center text-[13px] text-muted">{msg}</div>}
      </div>
      <p className="text-[11px] text-muted"
        title="All XAUS prices are indicative mid-market reference rates, not tradable broker quotes. Your broker's prices differ by the spread. The TradingView chart is TradingView's own widget (OANDA feed), a different source from the XAUS data the agents use. Times are your local time.">
        <b>Analysis only, not trading advice.</b> Indicative mid-market prices, not broker quotes · spot source {lp.source ?? '—'} via xaus.com ·{' '}
        {src === 'tv' ? 'Live ticks from TradingView (OANDA feed). Agents use XAUS data, so prices may differ by a few cents to dollars.'
          : src === 'spot' ? 'Live price checked every 15 s (it changes about once a minute)' : 'Futures candles refreshed every 60 s'}
      </p>
      {replay && <TradeReplay trade={replay} lot={ASSUMED_LOT} lotNote={replay.usd == null ? `Dollar amounts use an assumed ${ASSUMED_LOT} lot (a call does not record its lot).` : undefined} onClose={() => setReplay(null)} />}
    </div>
  )
}
