const MINUS = '\u2212'

/** Whole-dollar text: +$1,234 / −$5 / $0 / —. `sign:false` omits the plus on positives. */
export function money(v: number | null | undefined, opts: { sign?: boolean } = {}): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = opts.sign ?? true
  const r = Math.round(Math.abs(v))
  const body = `$${r.toLocaleString('en-US')}`
  if (r === 0) return body
  if (v < 0) return MINUS + body
  return (sign ? '+' : '') + body
}

/** R-multiple text: +1.23R / −0.50R / 0.00R / —. */
export function rtext(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  const s = Math.abs(v).toFixed(2)
  if (Number(s) === 0) return `${s}R`
  return `${v < 0 ? MINUS : '+'}${s}R`
}

/** Price with 2 decimals and thousands separator. */
export function price(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function toneOf(v: number | null | undefined): 'up' | 'dn' | '' {
  return v != null && v > 0 ? 'up' : v != null && v < 0 ? 'dn' : ''
}
