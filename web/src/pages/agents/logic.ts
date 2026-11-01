import type { AgentView, Track } from '../../api/types'

/** Old LABELS: short agent names. */
export const LABELS: Record<string, string> = {
  wyckoff: 'Wyckoff', elliott: 'Elliott', smc: 'Smart money', price_action: 'Price action', trend: 'Trend', macro: 'Macro',
  skeptic: 'Skeptic', sentiment: 'Psychology', stophunt: 'Stop-hunt', ict: 'ICT', psychology: 'Discipline',
}
export const labelOf = (k: string) => LABELS[k] || k

export type Kind = 'BUY' | 'SELL' | 'NA' | 'WAIT'
/** Old cls(): colour class of a bias / label text. */
export function cls(b: string | null | undefined): Kind {
  const s = b ?? ''
  return /BUY/.test(s) ? 'BUY' : /SELL/.test(s) ? 'SELL' : /SPLIT|NO DATA|NA|ERROR/.test(s) ? 'NA' : 'WAIT'
}
/** Old agentLabel(). */
export const agentLabel = (r: AgentView) => (r.status === 'OK' ? r.bias_label || r.bias : r.status === 'ERROR' ? 'ERROR' : 'NO DATA')

/** Old hitRate(). */
export function hitRate(track: Track | null | undefined, agent: string): string {
  const a = track?.agents?.[agent]
  if (!a) return 'track record: none yet'
  const decided = a.hits + a.misses
  return decided ? `${a.hit_rate}% right (${a.hits}/${decided})` : `track record: ${a.pending} waiting to be scored`
}

/** Old MOOD_CLS: crowd mood → colour class. */
export const MOOD_CLS: Record<string, Kind> = { PANIC: 'SELL', FEAR: 'NA', NEUTRAL: 'WAIT', GREED: 'NA', EUPHORIA: 'BUY' }

export const KIND_TEXT: Record<Kind, string> = { BUY: 'text-up', SELL: 'text-down', NA: 'text-warn', WAIT: 'text-text' }
export const KIND_BAR: Record<Kind, string> = { BUY: 'bg-up', SELL: 'bg-down', NA: 'bg-warn', WAIT: 'bg-accent' }

export const when = (t: number) =>
  new Date(t * 1000).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
