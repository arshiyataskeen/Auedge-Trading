import { useQuery } from '@tanstack/react-query'
import { xausGet } from './xaus'

export const SPOT_POLL_MS = 15000
export const STALE_AFTER_S = 180
const REF_POLL_MS = 10 * 60000

export type LivePrice = {
  price: number | null
  updatedAt: number | null // epoch seconds
  source: string | null
  status: 'loading' | 'live' | 'stale' | 'error' | 'noprice'
  change: { diff: number; pct: number } | null
}

type SpotReply = { spot_usd_oz?: number; xau?: { price?: number }; updated_at: string; price_source?: string }
type IntradayReply = { points?: { t: number; p: number | null }[] }

/**
 * Port of the old pollSpot / loadRef24 / updateChg: live spot price plus 24 h change.
 * Both reads are shared queries, so every caller (top bar, chart) uses one poller. A failed poll keeps the last price and flags the error.
 */
export function useLivePrice(): LivePrice {
  const spot = useQuery({
    queryKey: ['live', 'spot'], refetchInterval: SPOT_POLL_MS, retry: false, staleTime: 0,
    queryFn: async () => {
      const d = await xausGet<SpotReply>('/spot?compact=1')
      const price = d.spot_usd_oz ?? d.xau?.price
      if (price == null) throw new Error('NO_PRICE')
      const updatedAt = Date.parse(d.updated_at) / 1000
      return { price, updatedAt, source: d.price_source ?? null, fresh: Date.now() / 1000 - updatedAt <= STALE_AFTER_S }
    },
  })
  const ref = useQuery({
    queryKey: ['live', 'ref24'], refetchInterval: REF_POLL_MS, retry: false, staleTime: REF_POLL_MS,
    queryFn: async () => {
      const d = await xausGet<IntradayReply>('/intraday?symbol=xau&hours=48')
      const target = Date.now() / 1000 - 86400
      const pts = (d.points ?? []).filter((x) => x.p != null)
      if (!pts.length) return null
      return pts.reduce((b, x) => (Math.abs(x.t - target) < Math.abs(b.t - target) ? x : b)).p
    },
  })
  const s = spot.data
  const status: LivePrice['status'] = spot.isError ? (spot.error.message === 'NO_PRICE' ? 'noprice' : 'error') : s ? (s.fresh ? 'live' : 'stale') : 'loading'
  const ref24 = ref.data ?? null
  const change = s && ref24 != null && ref24 !== 0 ? { diff: s.price - ref24, pct: ((s.price - ref24) / ref24) * 100 } : null
  return { price: s?.price ?? null, updatedAt: s?.updatedAt ?? null, source: s?.source ?? null, status, change }
}
