/** Card surface used across the Backtest page (same `panel` token as the shared components). */
export const card = 'rounded border border-line bg-panel p-3'
export const sect = 'mb-2 text-[12px] font-semibold text-strong'
export const btn = 'rounded border border-line bg-panel2 px-3 py-1.5 text-[12.5px] text-strong hover:bg-hover disabled:opacity-50'
export const btnOn = 'rounded border border-accent bg-panel2 px-3 py-1.5 text-[12.5px] text-strong hover:bg-hover'
export const field = 'rounded border border-line bg-app px-2 py-1 text-[12.5px] text-strong'

export const ymd = (ts: number) => new Date(ts * 1000).toISOString().slice(0, 10)
export const dshort = (ts: number) => new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: '2-digit' })
export const dlong = (ts: number) => new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

export const LABELS: Record<string, string> = {
  wyckoff: 'Wyckoff', elliott: 'Elliott', smc: 'Smart money', price_action: 'Price action', trend: 'Trend', macro: 'Macro',
  skeptic: 'Skeptic', sentiment: 'Psychology', stophunt: 'Stop-hunt', ict: 'ICT', psychology: 'Discipline',
}

/** localStorage that never throws (private windows, blocked storage). */
export const lsGet = (k: string, d: string): string => { try { return localStorage.getItem(k) ?? d } catch { return d } }
export const lsSet = (k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* storage unavailable */ } }

export type Progress = { done: number; total: number; phase?: string }
export const pctOf = (p?: Progress) => (p && p.total ? Math.min(100, Math.round((100 * p.done) / p.total)) : 0)
