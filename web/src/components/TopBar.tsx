import { useEffect, useState } from 'react'
import { useLivePrice } from '../api/live'
import { price as fmt } from '../lib/format'
import { marketStatus } from '../lib/time'
import ThemeToggle from './ThemeToggle'

function market(nowMs: number) {
  const m = marketStatus(nowMs)
  if (m.open) return { text: 'MARKET OPEN', cls: 'text-up' }
  if (m.reason === 'daily break') return { text: 'DAILY BREAK', cls: 'text-warn' }
  return { text: `MARKET CLOSED · ${m.reason ?? 'closed'}`, cls: 'text-muted' }
}

const BADGE = {
  live: { text: 'LIVE', cls: 'bg-up-bg text-up' },
  stale: { text: 'STALE (market may be closed)', cls: 'bg-warn-bg text-warn' },
  error: { text: 'CONNECTION PROBLEM', cls: 'bg-down-bg text-down' },
  noprice: { text: 'NO PRICE AVAILABLE', cls: 'bg-down-bg text-down' },
  loading: { text: 'LOADING…', cls: 'bg-panel2 text-muted' },
} as const

export default function TopBar() {
  const lp = useLivePrice()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(id) }, [])
  const mk = market(now)
  const badge = BADGE[lp.status]
  const ch = lp.change
  const up = ch ? ch.diff >= 0 : true
  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-bg px-3">
      <b className="text-strong">XAUUSD</b>
      <span className="text-[18px] font-semibold text-strong">{lp.price != null ? `$${fmt(lp.price)}` : '—'}</span>
      {ch && (
        <span className={`text-[12px] ${up ? 'text-up' : 'text-down'}`}>
          {`${up ? '▲ +' : '▼ −'}${fmt(Math.abs(ch.diff))} (${up ? '+' : '−'}${Math.abs(ch.pct).toFixed(2)}%) 24h`}
        </span>
      )}
      <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${badge.cls}`}
        title={lp.updatedAt ? `Updated ${new Date(lp.updatedAt * 1000).toLocaleTimeString()} · source: ${lp.source ?? 'unknown'}` : undefined}>
        {badge.text}
      </span>
      <span className={`text-[11px] max-sm:hidden ${mk.cls}`}>{mk.text}</span>
      <span className="ml-auto"><ThemeToggle /></span>
    </header>
  )
}
