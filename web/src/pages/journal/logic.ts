import type { AccountBody, JournalAccount, JournalTrade, Side, TradeBody } from '../../api/types'

/* Pure helpers ported from static/journal.js (PRESETS, EMOTIONS, SETUPS, readPhases/readRules, tradeBody, riskHint, readImg, recFiltered, downloadCsv). */

export const EMOTIONS = ['Calm', 'Confident', 'Patient', 'Fearful', 'Greedy', 'FOMO', 'Revenge', 'Tired', 'Bored']
export const SETUPS = ['AuEdge NOW call', 'Stop hunt + reclaim', 'London sweep', 'Breakout', 'Pullback to level', 'Range fade', 'News']

export const jDate = (ts: number | null | undefined) =>
  ts ? new Date(ts * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'
export const jDay = (ts: number | null | undefined) =>
  ts ? new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
export const toLocalInput = (ts: number | null | undefined) =>
  ts ? new Date(ts * 1000 - new Date(ts * 1000).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : ''
export const fromLocalInput = (v: string) => (v ? Math.round(Date.parse(v) / 1000) : null)

/* ---------- account rules form (all values are the raw input strings, exactly what the old form posted) ---------- */
export type PhaseRow = {
  name: string; target_pct: string; daily_loss_pct: string; max_loss_pct: string; max_loss_type: string; min_days: string; consistency_pct: string
}
export type FundedRow = { daily_loss_pct: string; max_loss_pct: string; max_loss_type: string; profit_split: string; consistency_pct: string }
export type RulesForm = { phases: PhaseRow[]; funded: FundedRow; reset: string; daily_base: string }

const row = (name: string, target: string, d: string, m: string, type: string, days: string): PhaseRow =>
  ({ name, target_pct: target, daily_loss_pct: d, max_loss_pct: m, max_loss_type: type, min_days: days, consistency_pct: '' })
const fund = (d: string, m: string, type: string, split: string): FundedRow =>
  ({ daily_loss_pct: d, max_loss_pct: m, max_loss_type: type, profit_split: split, consistency_pct: '' })

export type PresetKey = 'two' | 'one' | 'blank'
export const PRESETS: Record<PresetKey, { label: string; phases: PhaseRow[]; funded: FundedRow }> = {
  two: { label: 'Common 2-step', phases: [row('Phase 1', '10', '5', '10', 'static', '4'), row('Phase 2', '5', '5', '10', 'static', '4')],
    funded: fund('5', '10', 'static', '80') },
  one: { label: '1-step', phases: [row('Phase 1', '10', '4', '6', 'trailing', '3')], funded: fund('4', '6', 'trailing', '80') },
  blank: { label: 'Blank', phases: [row('Phase 1', '', '', '', 'static', '0')], funded: fund('', '', 'static', '') },
}

export const blankRules = (): RulesForm => ({
  phases: PRESETS.blank.phases.map((p) => ({ ...p })), funded: { ...PRESETS.blank.funded }, reset: 'utc', daily_base: 'initial',
})
const s = (v: unknown) => (v == null ? '' : String(v))
export function rulesFromAccount(a: JournalAccount): RulesForm {
  const f = a.rules.funded
  return {
    phases: a.rules.phases.map((p) => ({
      name: p.name, target_pct: s(p.target_pct), daily_loss_pct: s(p.daily_loss_pct), max_loss_pct: s(p.max_loss_pct),
      max_loss_type: p.max_loss_type === 'trailing' ? 'trailing' : 'static', min_days: p.min_days == null ? '0' : String(p.min_days),
      consistency_pct: s(p.consistency_pct),
    })),
    funded: { daily_loss_pct: s(f.daily_loss_pct), max_loss_pct: s(f.max_loss_pct), max_loss_type: f.max_loss_type === 'trailing' ? 'trailing' : 'static',
      profit_split: s(f.profit_split), consistency_pct: s(f.consistency_pct) },
    reset: a.rules.reset || 'utc', daily_base: a.rules.daily_base || 'initial',
  }
}
/** Preset click: replaces the phases and four funded fields; the funded consistency %, reset and base stay as typed. */
export const applyPreset = (f: RulesForm, k: PresetKey): RulesForm => {
  const P = PRESETS[k]
  return { ...f, phases: P.phases.map((p) => ({ ...p })), funded: { ...P.funded, consistency_pct: f.funded.consistency_pct } }
}
export const MAX_PHASES = 5
export function addPhase(ps: PhaseRow[]): PhaseRow[] {
  if (ps.length >= MAX_PHASES) return ps
  const l: Partial<PhaseRow> = ps[ps.length - 1] ?? {}
  return [...ps, { name: `Phase ${ps.length + 1}`, target_pct: '', daily_loss_pct: l.daily_loss_pct ?? '', max_loss_pct: l.max_loss_pct ?? '',
    max_loss_type: l.max_loss_type ?? 'static', min_days: l.min_days ?? '', consistency_pct: l.consistency_pct ?? '' }]
}
export const removePhase = (ps: PhaseRow[], i: number) => (ps.length <= 1 ? ps : ps.filter((_, j) => j !== i))

/** Old readRules(). */
export const readRules = (f: RulesForm) => ({
  phases: f.phases.map((p) => ({ name: p.name, target_pct: p.target_pct, daily_loss_pct: p.daily_loss_pct, max_loss_pct: p.max_loss_pct,
    max_loss_type: p.max_loss_type, min_days: p.min_days, consistency_pct: p.consistency_pct })),
  funded: { daily_loss_pct: f.funded.daily_loss_pct, max_loss_pct: f.funded.max_loss_pct, max_loss_type: f.funded.max_loss_type,
    profit_split: f.funded.profit_split, consistency_pct: f.funded.consistency_pct },
  reset: f.reset, daily_base: f.daily_base,
})
export const accountBody = (v: { name: string; firm: string; size: string; notes: string }, rules: RulesForm): AccountBody =>
  ({ name: v.name.trim(), firm: v.firm.trim(), size: +v.size, notes: v.notes, rules: readRules(rules) })

/* ---------- trade form ---------- */
export type TradeValues = Partial<Omit<JournalTrade, 'stop' | 'target'>> & { stop?: number | null; target?: number | null; side: Side; symbol: string; opened_at: number }
export type TradeFormState = {
  acc: string; phase: string; symbol: string; side: Side; opened: string; closed: string
  lots: string; entry: string; stop: string; target: string; exit: string; pnl: string; com: string; setup: string
  plan: number | null; rate: number; mood: string | null; mist: string; notes: string
  /** null = untouched, "remove" = delete the saved screenshot, otherwise a data URL */
  image: string | null
}
const nv = (v: unknown) => (v == null ? '' : String(v))
export function initialTrade(v: TradeValues, accId: number | undefined, phaseId: number | undefined): TradeFormState {
  return {
    acc: nv(accId), phase: nv(phaseId), symbol: v.symbol, side: v.side, opened: toLocalInput(v.opened_at), closed: toLocalInput(v.closed_at),
    lots: nv(v.lots), entry: nv(v.entry), stop: nv(v.stop), target: nv(v.target), exit: nv(v.exit), pnl: nv(v.pnl),
    com: v.commission ? String(v.commission) : '', setup: v.setup || '', plan: v.followed_plan ?? null, rate: v.rating || 0,
    mood: v.emotion || null, mist: v.mistakes || '', notes: v.notes || '', image: null,
  }
}
/** Old tradeBody(). `src` carries the untouched source / auedge fields of the form's initial values. */
export function tradeBody(f: TradeFormState, src: { source?: string; auedge?: unknown }): TradeBody {
  const n = (x: string) => (x === '' ? null : +x)
  return {
    account_id: +f.acc, phase_id: +f.phase, symbol: f.symbol, side: f.side,
    opened_at: fromLocalInput(f.opened), closed_at: fromLocalInput(f.closed), lots: n(f.lots), entry: n(f.entry),
    stop: n(f.stop), target: n(f.target), exit: n(f.exit), pnl: n(f.pnl), commission: n(f.com), setup: f.setup,
    followed_plan: f.plan, rating: f.rate || null, emotion: f.mood, mistakes: f.mist, notes: f.notes,
    source: src.source, auedge: src.auedge, image_data: f.image,
  }
}
/** Old riskHint() numbers (gold: 1 lot = 100 oz). */
export function riskNumbers(a: JournalAccount | undefined, f: TradeFormState) {
  if (!a) return null
  const c = a.current?.check
  const lots = +f.lots, e = +f.entry, st = +f.stop, ex = +f.exit
  const out: { risk?: number; riskPct?: number; room?: number | null; over?: boolean; lots05?: number; lots1?: number; pnl?: number } = {}
  if (lots && e && st) {
    out.risk = Math.abs(e - st) * lots * 100
    out.riskPct = (100 * out.risk) / a.size
    if (c && c.daily_room != null) { out.room = c.daily_room; out.over = out.risk > c.daily_room }
  }
  if (e && st) {
    const perLot = Math.abs(e - st) * 100
    out.lots05 = (a.size * 0.005) / perLot
    out.lots1 = (a.size * 0.01) / perLot
  }
  if (lots && e && ex && f.pnl === '') out.pnl = Math.round((ex - e) * (f.side === 'BUY' ? 1 : -1) * lots * 100 * 100) / 100
  return out
}

/** Old readImg(): the file as a data URL; over 6 MB is refused. */
export const MAX_IMG = 6 * 1024 * 1024
export function readImage(file: File): Promise<string> {
  if (file.size > MAX_IMG) return Promise.reject(new Error('Screenshot must be under 6 MB.'))
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result))
    r.onerror = () => reject(new Error('Could not read the image.'))
    r.readAsDataURL(file)
  })
}

/* ---------- All records ---------- */
export type RecFilters = { acc?: string; phase?: string; side?: string; setup?: string; res?: string; from?: string; to?: string; q?: string }
export function recFiltered(trades: JournalTrade[], f: RecFilters): JournalTrade[] {
  return trades.filter((t) => (!f.acc || t.account_id === +f.acc) && (!f.phase || t.phase === f.phase) && (!f.side || t.side === f.side)
    && (!f.setup || (t.setup || '') === f.setup)
    && (!f.res || (f.res === 'win' ? t.net > 0 : f.res === 'loss' ? t.net < 0 : t.net == null))
    && (!f.from || t.day >= f.from) && (!f.to || t.day <= f.to)
    && (!f.q || `${t.notes ?? ''} ${t.mistakes ?? ''} ${t.setup ?? ''} ${t.emotion ?? ''}`.toLowerCase().includes(f.q.toLowerCase())))
}

export const CSV_COLS = ['day', 'opened_at', 'closed_at', 'account', 'phase', 'symbol', 'side', 'lots', 'entry', 'stop', 'target', 'exit', 'pnl',
  'commission', 'net', 'planned_rr', 'r', 'setup', 'emotion', 'followed_plan', 'rating', 'source', 'mistakes', 'notes']
export function csvText(rows: JournalTrade[]): string {
  const iso = (ts: unknown) => (ts ? new Date((ts as number) * 1000).toISOString() : '')
  const cell = (v: unknown) => { const x = v == null ? '' : String(v); return /[",\n]/.test(x) ? `"${x.replace(/"/g, '""')}"` : x }
  const rec = (t: JournalTrade) => t as unknown as Record<string, unknown>
  return [CSV_COLS.join(',')].concat(rows.map((t) => CSV_COLS.map((c) => cell(c.endsWith('_at') ? iso(rec(t)[c]) : rec(t)[c])).join(','))).join('\n')
}
export function downloadCsv(rows: JournalTrade[]) {
  const url = URL.createObjectURL(new Blob([csvText(rows)], { type: 'text/csv' }))
  const el = Object.assign(document.createElement('a'), { href: url, download: `auedge-journal-${new Date().toISOString().slice(0, 10)}.csv` })
  document.body.appendChild(el); el.click(); el.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}
