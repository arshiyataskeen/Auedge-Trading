import { localDay } from './time'

export type Agg = { pnl: number; n: number; won: number; lost: number; idx: number[]; bal: number | null }
export type TradeLike = { exit_t: number; r: number; usd?: number | null; balance?: number | null }
export type Groups = {
  years: Map<string, Agg>
  months: Map<string, Agg>
  days: Map<string, Agg>
  /** True when every trade has a dollar result, so pnl is in dollars; otherwise pnl is in R. */
  hasUsd: boolean
}

const blank = (): Agg => ({ pnl: 0, n: 0, won: 0, lost: 0, idx: [], bal: null })

function bump(map: Map<string, Agg>, key: string, v: number, t: TradeLike, i: number) {
  let x = map.get(key)
  if (!x) { x = blank(); map.set(key, x) }
  x.pnl += v
  x.n++
  if (t.r > 0) x.won++
  else if (t.r < 0) x.lost++
  x.idx.push(i)
  if (t.balance != null) x.bal = t.balance
}

/** Port of the old btGroups: year / month / local-day totals keyed by the local day of `exit_t`. */
export function groupTrades(trades: TradeLike[]): Groups {
  const g: Groups = { years: new Map(), months: new Map(), days: new Map(), hasUsd: trades.every((t) => t.usd != null) }
  trades.forEach((t, i) => {
    const k = localDay(t.exit_t)
    const v = t.usd ?? t.r
    bump(g.years, k.slice(0, 4), v, t, i)
    bump(g.months, k.slice(0, 7), v, t, i)
    bump(g.days, k, v, t, i)
  })
  return g
}

export const sortedKeys = (m: Map<string, unknown>) => [...m.keys()].sort()
