import type { BtTrade, DemoTrade } from '../../api/types'

/** Port of demoPnl (mirrors core/track.py): half closed at 1R, the rest marked to the live spot price. */
export function demoPnl(t: Pick<DemoTrade, 'side' | 'lot' | 'cost' | 'entry' | 'stop' | 'half'> & { be?: number }, price: number): number {
  const s = t.side === 'BUY' ? 1 : -1, oz = 100 * (t.lot || 0.1), cost = t.cost || 0
  const be = t.be ?? t.entry + s * Math.abs(t.entry - t.stop)
  const rest = (price - s * cost - t.entry) * s * oz
  return Math.round((t.half ? 0.5 * (be - s * cost - t.entry) * s * oz + 0.5 * rest : rest) * 100) / 100
}

/** liveDemoTick: every open position's unrealised P&L from the live price; equity = balance + their sum. */
export function withLivePrice(open: DemoTrade[], balance: number, equity: number, price: number | null) {
  if (price == null || !open.length) return { open, equity }
  const next = open.map((t) => ({ ...t, unrealised: demoPnl(t, price) }))
  return { open: next, equity: balance + next.reduce((a, t) => a + (t.unrealised ?? 0), 0) }
}

/** Port of demoToTrade: demo rows are in SPOT prices; `gap` shifts the futures candles to spot for the chart. */
export function demoToTrade(t: DemoTrade): BtTrade & { lot: number } {
  const open = t.status === 'open'
  return {
    side: t.side, kind: 'now', decided_t: Math.floor(t.ts), entry_t: Math.floor(t.ts),
    exit_t: t.closed_ts ? Math.floor(t.closed_ts) : 0, entry: t.entry, stop: t.stop, t1: t.t1, exit: t.exit_price ?? 0,
    r: t.result_r ?? 0, gap: t.gap || 0, half: !!t.half, lot: t.lot,
    usd: open ? t.unrealised : t.usd,
    why: open ? (t.half ? 'open · half taken at 1R, stop at entry' : 'open') : (t.why || t.status),
    open,
  }
}

export const hm = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
