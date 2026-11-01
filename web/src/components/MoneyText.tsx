import { money, rtext, toneOf } from '../lib/format'

const TONE = { up: 'text-up', dn: 'text-down', '': '' } as const

/** Coloured, tabular money (default) or R text (`r`). */
export default function MoneyText({ v, r = false, sign }: { v: number | null | undefined; r?: boolean; sign?: boolean }) {
  const text = r ? rtext(v) : money(v, sign === undefined ? {} : { sign })
  return <span className={`tabular-nums ${TONE[toneOf(v)]}`.trim()}>{text}</span>
}
