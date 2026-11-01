const API = 'https://xaus.com/api/v1'

/** GET on the free XAUS API (spot samples, futures candles). A 503 means the service has no price right now. */
export async function xausGet<T>(path: string): Promise<T> {
  const r = await fetch(API + path, { cache: 'no-store' })
  if (r.status === 503) throw new Error('NO_PRICE')
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json() as Promise<T>
}
