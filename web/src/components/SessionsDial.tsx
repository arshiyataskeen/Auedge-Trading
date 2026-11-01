import { useEffect, useState } from 'react'
import { goldWeekendClosed, sessionStatuses, span } from '../lib/sessions'

const R = 62, C = 2 * Math.PI * R

/** 24-hour ring with a current-time hand, digital time and 4 session chips. */
export default function SessionsDial() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 15000); return () => clearInterval(id) }, [])
  const d = new Date(now)
  const frac = (d.getHours() * 60 + d.getMinutes()) / 1440
  const closed = goldWeekendClosed(now)
  const st = sessionStatuses(now)
  const openN = st.filter((s) => s.isOpen)
  const status = closed ? 'Weekend: market closed' : openN.length ? `Open: ${openN.map((s) => s.name).join(' + ')}` : 'Between sessions'
  return (
    <section data-testid="sessions-dial" className="w-full rounded-xl border border-line bg-panel p-4">
      <div className="label-caps mb-3">Market sessions now</div>
      <div className="flex flex-wrap items-center gap-5">
        <div className="relative h-[160px] w-[160px] shrink-0">
          <svg viewBox="0 0 160 160" className="h-full w-full" role="img" aria-label="24-hour clock">
            <circle cx="80" cy="80" r={R} fill="none" stroke="var(--line2)" strokeWidth="10" />
            <circle cx="80" cy="80" r={R} fill="none" stroke={closed ? 'var(--faint)' : 'var(--up)'} strokeWidth="10" strokeLinecap="round"
              strokeDasharray={`${C * frac} ${C}`} transform="rotate(-90 80 80)" />
            {[0, 6, 12, 18].map((h) => {
              const a = (h / 24) * 2 * Math.PI - Math.PI / 2
              return <text key={h} x={80 + 76 * Math.cos(a)} y={80 + 76 * Math.sin(a) + 3} textAnchor="middle" fontSize="8" fill="var(--muted)">{h}</text>
            })}
            <line data-testid="dial-hand" x1="80" y1="80" x2="80" y2="26" stroke="var(--strong)" strokeWidth="2" strokeLinecap="round" transform={`rotate(${frac * 360} 80 80)`} />
            <circle cx="80" cy="80" r="4" fill="var(--strong)" />
          </svg>
          <div className="pointer-events-none absolute inset-x-0 bottom-6 text-center text-[15px] font-bold tabular-nums text-strong">
            {d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
        </div>
        <div className="min-w-[200px] flex-1">
          <div data-testid="dial-status" className={`mb-3 text-[18px] font-extrabold ${closed ? 'text-muted' : 'text-strong'}`}>{status}</div>
          <div className="grid grid-cols-2 gap-2">
            {st.map((s) => (
              <div key={s.key} data-testid={`chip-${s.key}`} className="rounded-xl border border-line bg-panel2 px-3 py-2">
                <div className="flex items-center justify-between text-[12px] font-semibold text-strong">
                  {s.name}<span className={`text-[10px] font-bold uppercase tracking-wider ${s.isOpen ? 'text-up' : 'text-muted'}`}>{s.isOpen ? 'Open' : 'Closed'}</span>
                </div>
                <div className="text-[11px] text-muted">{s.isOpen ? 'closes in' : 'opens in'} {Number.isFinite(s.flipIn) ? span(s.flipIn) : '-'}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
