import { useEffect, useState } from 'react'

const API = 'https://xaus.com/api/v1'
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

async function getJSON(path: string) {
  const r = await fetch(API + path, { cache: 'no-store' })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

/** Port of the old pollSpot / loadRef24 / updateChg: live spot price plus 24 h change. */
export function useLivePrice(): LivePrice {
  const [spot, setSpot] = useState<Pick<LivePrice, 'price' | 'updatedAt' | 'source' | 'status'>>({ price: null, updatedAt: null, source: null, status: 'loading' })
  const [ref24, setRef24] = useState<number | null>(null)

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const d = await getJSON('/spot?compact=1')
        const price: number | undefined = d.spot_usd_oz ?? d.xau?.price
        if (price == null) throw new Error('NO_PRICE')
        const updatedAt = Date.parse(d.updated_at) / 1000
        const fresh = Date.now() / 1000 - updatedAt <= STALE_AFTER_S
        if (alive) setSpot({ price, updatedAt, source: d.price_source ?? null, status: fresh ? 'live' : 'stale' })
      } catch (e) {
        if (alive) setSpot((s) => ({ ...s, status: (e as Error).message === 'NO_PRICE' ? 'noprice' : 'error' }))
      }
    }
    poll()
    const id = setInterval(poll, SPOT_POLL_MS)
    return () => { alive = false; clearInterval(id) }
  }, [])

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const d = await getJSON('/intraday?symbol=xau&hours=48')
        const target = Date.now() / 1000 - 86400
        const pts = ((d.points ?? []) as { t: number; p: number | null }[]).filter((x) => x.p != null)
        if (!pts.length) return
        const best = pts.reduce((b, x) => (Math.abs(x.t - target) < Math.abs(b.t - target) ? x : b))
        if (alive) setRef24(best.p)
      } catch { /* keep previous reference */ }
    }
    load()
    const id = setInterval(load, REF_POLL_MS)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const change = spot.price != null && ref24 != null && ref24 !== 0
    ? { diff: spot.price - ref24, pct: ((spot.price - ref24) / ref24) * 100 } : null
  return { ...spot, change }
}
