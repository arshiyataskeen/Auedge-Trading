import type { AgentView, BtTrade, Chief, StopPool, TradePlan, XausChart, XausIntraday } from '../../api/types'
import { nyTradingDay } from '../../lib/time'

/* ================= timeframes and candles ================= */

export type TfName = '1m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d'
export type Src = 'tv' | 'spot' | 'fut'
type FutCfg = { interval: string; range: string; aggregate?: boolean }
/** Old TF table. Spot history comes from 2-5 min samples, so 1m / 1d spot is impossible. */
export const TF: Record<TfName, { sec: number; spot: boolean; fut: FutCfg }> = {
  '1m': { sec: 60, spot: false, fut: { interval: '1m', range: '1d' } },
  '5m': { sec: 300, spot: true, fut: { interval: '5m', range: '5d' } },
  '15m': { sec: 900, spot: true, fut: { interval: '15m', range: '1mo' } },
  '30m': { sec: 1800, spot: true, fut: { interval: '30m', range: '1mo' } },
  '1h': { sec: 3600, spot: true, fut: { interval: '1h', range: '3mo' } },
  '4h': { sec: 14400, spot: true, fut: { interval: '1h', range: '3mo', aggregate: true } },
  '1d': { sec: 86400, spot: false, fut: { interval: '1d', range: '1y' } },
}
export const TF_NAMES = Object.keys(TF) as TfName[]
export const DEFAULT_SAMPLE_SEC = 300

/** Only offer spot timeframes whose candles hold at least 3 samples (XAUS changed its sampling once already). */
export const spotOk = (tf: TfName, sampleSec: number) => TF[tf].spot && TF[tf].sec >= 3 * sampleSec
export const firstSpotTf = (sampleSec: number): TfName => TF_NAMES.find((n) => spotOk(n, sampleSec)) ?? '1h'

export type Bar = { time: number; open: number; high: number; low: number; close: number; volume: number }
type Pt = { t: number; p?: number | null; o?: number | null; h?: number | null; l?: number | null; c?: number | null; v?: number | null }

/** Group raw points into candles of `sec` seconds. Each input has t plus either p (sample) or o/h/l/c/v (bar). */
export function aggregate(points: Pt[], sec: number): Bar[] {
  const out: Bar[] = []
  for (const pt of points) {
    const time = Math.floor(pt.t / sec) * sec
    const o = pt.o ?? pt.p, h = pt.h ?? pt.p, l = pt.l ?? pt.p, c = pt.c ?? pt.p, v = pt.v ?? 0
    if (o == null || c == null || h == null || l == null) continue
    const last = out[out.length - 1]
    if (last && last.time === time) {
      last.high = Math.max(last.high, h); last.low = Math.min(last.low, l); last.close = c; last.volume += v
    } else out.push({ time, open: o, high: h, low: l, close: c, volume: v })
  }
  return out
}

/** Old loadSpot: the sample period is the larger of what the API says and the measured median gap. */
export function spotSampleSec(d: XausIntraday): number {
  const pts = d.points.filter((p) => p.p != null)
  const gaps = pts.slice(-30).map((p, i, a) => (i ? p.t - a[i - 1].t : 0)).slice(1).sort((x, y) => x - y)
  const measured = gaps.length ? Math.round(gaps[gaps.length >> 1] / 60) * 60 : 0
  return Math.max(d.interval_seconds || 0, measured, 60)
}

/** Old addSpotTick: the live price updates the newest candle or opens the next one. Returns the same array when ignored. */
export function withTick(bars: Bar[], price: number, t: number, sec: number): Bar[] {
  const last = bars[bars.length - 1]
  if (!last) return bars
  const time = Math.floor(t / sec) * sec
  if (time < last.time) return bars
  if (time === last.time) return [...bars.slice(0, -1), { ...last, high: Math.max(last.high, price), low: Math.min(last.low, price), close: price }]
  return [...bars, { time, open: price, high: price, low: price, close: price, volume: 0 }]
}

export function futuresBars(d: XausChart, tf: TfName): Bar[] {
  const cfg = TF[tf].fut
  const pts = d.points.filter((p) => p.o != null && p.c != null)
  return cfg.aggregate ? aggregate(pts, TF[tf].sec)
    : pts.map((p) => ({ time: p.t, open: p.o!, high: p.h, low: p.l, close: p.c!, volume: p.v || 0 }))
}

export function ago(sec: number): string {
  if (sec < 90) return `${Math.round(sec)} s ago`
  if (sec < 5400) return `${Math.round(sec / 60)} min ago`
  if (sec < 172800) return `${(sec / 3600).toFixed(1)} h ago`
  return `${Math.round(sec / 86400)} days ago`
}

/** Seconds left in the current candle of `tfSec`. */
export const leftSec = (tfSec: number, nowSec: number) => tfSec - (Math.floor(nowSec) % tfSec)
/** Old fmtLeft: m:ss, or h:mm:ss from an hour up. */
export function fmtLeft(tfSec: number, nowSec: number): string {
  const left = leftSec(tfSec, nowSec)
  const h = Math.floor(left / 3600), mm = Math.floor((left % 3600) / 60), s = left % 60
  return `${h ? `${h}:${String(mm).padStart(2, '0')}` : mm}:${String(s).padStart(2, '0')}`
}

export const tzShift = () => -new Date().getTimezoneOffset() * 60 // chart library shows UTC, so shift to local
/** Old callBar: the candle (in chart time) that a timestamp falls into. */
export const callBar = (ts: number, sec: number) => Math.floor(ts / sec) * sec + tzShift()

/* ================= chart overlays ================= */

export type LevelLine = { price: number; color: string; style: number; title: string; width: number }
/** Old drawLevels: stop pools and the Chief's plan, drawn on the Spot chart (agent prices are spot prices). Style: 0 solid, 1 dotted, 2 dashed, 3 large dashed. */
export function chartLevels(c: Chief): LevelLine[] {
  const out: LevelLine[] = []
  const add = (price: number, color: string, style: number, title: string, width = 1) => out.push({ price, color, style, title, width })
  const pool = (p: StopPool, name: string) => add(p.price, p.status === 'hunted' ? '#6b7280' : '#f0b429', 3, p.status === 'hunted' ? 'HUNTED' : name)
  c.stops_above.slice(0, 3).forEach((p) => pool(p, 'BUY STOPS'))
  c.stops_below.slice(0, 3).forEach((p) => pool(p, 'SELL STOPS'))
  const plan = c.plan
  if (plan.stop != null && plan.entry_lo != null && plan.entry_hi != null) {
    add((plan.entry_lo + plan.entry_hi) / 2, '#4c8dff', 2, plan.kind === 'now' ? 'ENTRY' : 'ENTRY IF', 2)
    add(plan.stop, '#ef5350', 0, 'STOP', 2)
    if (plan.t1 != null) add(plan.t1, '#26a69a', 2, 'TARGET 1', 2)
    if (plan.be_at != null) add(plan.be_at, '#26a69a', 1, 'HALF @1R', 1)
  }
  return out
}

export type CallMarker = { time: number; position: 'aboveBar' | 'belowBar'; color: string; shape: 'arrowUp' | 'arrowDown' | 'circle'; text: string }
/** Old applyCallMarkers: an arrow at each call's entry candle and a circle at its exit, for candles that are on the chart. */
export function callMarkers(calls: BtTrade[], barTimes: number[], sec: number, fmt: (n: number) => string, usd: (n: number) => string): CallMarker[] {
  const have = new Set(barTimes.map((t) => t + tzShift())), out: CallMarker[] = []
  for (const t of calls) {
    const s = t.side === 'BUY' ? 1 : -1, tag = t.source === 'demo' ? 'DEMO ' : ''
    const a = callBar(t.entry_t, sec)
    if (have.has(a)) out.push({ time: a, position: s > 0 ? 'belowBar' : 'aboveBar', color: s > 0 ? '#089981' : '#f23645', shape: s > 0 ? 'arrowUp' : 'arrowDown', text: `${tag}${t.side} ${fmt(t.entry)}` })
    if (t.exit_t) {
      const b = callBar(t.exit_t - 1, sec)
      if (have.has(b)) out.push({
        time: b, position: s > 0 ? 'aboveBar' : 'belowBar', color: (t.usd ?? t.r) >= 0 ? '#26a69a' : '#ef5350', shape: 'circle',
        text: t.usd != null ? usd(t.usd) : `${t.r > 0 ? '+' : ''}${t.r}R`,
      })
    }
  }
  return out.sort((x, y) => x.time - y.time)
}

/* ================= plan helpers ================= */

/** Old sizeText: risk a fixed % of the account between entry and stop; 1 lot = 100 oz. */
export function sizeInfo(plan: TradePlan | null | undefined, acct: number, riskPct: number) {
  if (!plan || plan.stop == null || plan.entry_lo == null || plan.entry_hi == null) return null
  const entry = (plan.entry_lo + plan.entry_hi) / 2, dist = Math.abs(entry - plan.stop)
  if (!(acct > 0) || !(riskPct > 0) || !(dist > 0)) return null
  const riskUsd = (acct * riskPct) / 100, oz = riskUsd / dist
  return { acct, riskPct, riskUsd, oz, lots: oz / 100 }
}

export type LevelRow = { price: number; kind: string; kcls: 'entry' | 'stop' | 'target' | 'pool' | 'other'; src: string; note: string }
/** Old Levels tab: every price level from the plan, stop map and agents, highest first. Day view keeps those within one average day's move (and the Chief's own). */
export function levelRows(c: Chief, agents: AgentView[], p: number | null, mode: 'day' | 'all'): { rows: LevelRow[]; total: number; day: boolean } {
  const plan = c.plan, rows: LevelRow[] = []
  const add = (price: number | null | undefined, kind: string, kcls: LevelRow['kcls'], src: string, note: string) => {
    if (price != null) rows.push({ price, kind, kcls, src, note })
  }
  if (plan.stop != null) {
    add(plan.entry_hi, 'entry', 'entry', 'Chief plan', plan.kind === 'now' ? 'entry zone top' : 'entry if hunted (top)')
    if (plan.entry_lo !== plan.entry_hi) add(plan.entry_lo, 'entry', 'entry', 'Chief plan', 'entry zone bottom')
    add(plan.stop, 'stop', 'stop', 'Chief plan', 'stop loss')
    add(plan.t1, 'target', 'target', 'Chief plan', 'target 1')
    add(plan.be_at, 'target', 'target', 'Chief plan', 'half off at 1R, then stop to entry')
  }
  c.stops_above.forEach((x) => add(x.price, x.status === 'hunted' ? 'hunted' : 'buy stops', 'pool', 'Stop map', x.sources.join(', ')))
  c.stops_below.forEach((x) => add(x.price, x.status === 'hunted' ? 'hunted' : 'sell stops', 'pool', 'Stop map', x.sources.join(', ')))
  agents.forEach((a) => (a.levels || []).forEach((l) =>
    add(l.price, l.kind, (['stop', 'target', 'entry'].includes(l.kind) ? l.kind : 'other') as LevelRow['kcls'], a.label ?? a.agent, (l.note || '').replace(' (≈ spot, converted from futures)', ''))))
  rows.sort((a, b) => b.price - a.price)
  const total = rows.length, rng = c.day_range, day = mode !== 'all' && !!rng && p != null
  return { rows: day ? rows.filter((r) => r.src === 'Chief plan' || Math.abs(r.price - p!) <= rng) : rows, total, day }
}

/* ================= discipline coach (kept in this browser, same keys as the old page) ================= */

export const MY_MAX_TRADES = 2, MY_MAX_LOSSES = 2
export type MyDay = { day: string; trades: number; losses: number }
export const CHECKS: [string, string][] = [
  ['risk', 'I accept losing the risk amount on this trade, calmly'],
  ['news', 'No CPI, jobs report or Fed news in the next 30 minutes'],
  ['revenge', 'I am not trying to win back an earlier loss'],
  ['stop', 'I will set the stop now and never move it further away'],
]
/** Gold's trading day starts 18:00 New York. */
export const tradingDay = () => nyTradingDay(Date.now() / 1000)
export function parseMyDay(raw: string | null): MyDay {
  try { const v = JSON.parse(raw ?? '{}'); if (v.day === tradingDay()) return { day: v.day, trades: +v.trades || 0, losses: +v.losses || 0 } } catch { /* start fresh */ }
  return { day: tradingDay(), trades: 0, losses: 0 }
}
export type Checks = { at?: string } & Record<string, boolean | string | undefined>
export function parseChecks(raw: string | null, genAt: string): Checks {
  try { const c = JSON.parse(raw ?? '{}'); return c.at === genAt ? c : { at: genAt } } catch { return { at: genAt } }
}

export { readStored, useStored, writeStored } from '../../lib/stored'
