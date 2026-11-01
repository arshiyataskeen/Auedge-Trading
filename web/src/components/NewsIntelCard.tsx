import { money, price } from '../lib/format'

/* eslint-disable @typescript-eslint/no-explicit-any */
type Extra = Record<string, any> | undefined
const pct = (v: unknown) => `${Math.round((Number(v) || 0) * 100)}%`
const sgn = (z: number | null | undefined) => (z == null ? '—' : `${z < 0 ? '−' : '+'}${Math.abs(z).toFixed(1)}`)
const when = (t: number) => new Date(t * 1000).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })
const SHELL = 'rounded border border-line bg-panel p-3 text-[13px]'
const LAB = 'text-[11px] font-semibold uppercase tracking-[.06em] text-muted'

/** Advisory news intelligence: event, typical first-hour move, chances, similar releases. `avoid` = the agent row's AVOID label. */
export default function NewsIntelCard({ extra, compact = false, avoid = false }: { extra: Extra; compact?: boolean; avoid?: boolean }) {
  if (!extra) {
    return (
      <section className={SHELL}>
        <h3 className="text-[12px] font-semibold text-strong">News intelligence</h3>
        <p className="mt-1 text-muted">News intelligence is not available right now.</p>
      </section>
    )
  }
  const ev = extra.event as { name: string; t: number } | null | undefined
  const live = extra.mode === 'live'
  const p = extra.probs as { down: number; side: number; up: number } | null | undefined
  const range = extra.expected_range as [number, number] | null | undefined
  const sim = (extra.similar ?? []) as { date?: string; t?: number; kind: string; z: number | null; move60: number }[]
  const m5 = extra.m5 as { bos?: string; retest?: string; text?: string } | undefined
  const label = extra.phase === 'post' ? 'after the release' : 'before the release'
  return (
    <section data-testid="news-intel" className={SHELL}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[12px] font-semibold text-strong">News intelligence</h3>
        {avoid && <span className="rounded bg-down-bg px-1.5 py-px text-[10.5px] font-bold text-down">AVOID</span>}
        {extra.uncertain && <span className="rounded bg-warn-bg px-1.5 py-px text-[10.5px] font-semibold text-warn">uncertain</span>}
      </div>
      {!ev ? (
        <p className="mt-1 text-muted">No major US release in the next 24 hours, so there is no news context.</p>
      ) : (
        <div className="mt-1.5">
          <b className="font-semibold">{ev.name}</b>
          <span className="ml-1.5 text-[11.5px] text-muted">{when(ev.t)} · {label}</span>
          {extra.others?.length ? <div className="text-[11.5px] text-muted">also: {extra.others.join(', ')}</div> : null}
        </div>
      )}
      {ev && extra.expected_move != null && (
        <div className="mt-2">
          <div className={LAB}>Typical first-hour move</div>
          <div className="tabular-nums">
            about {money(extra.expected_move, { sign: false })}
            {range && <span className="ml-1.5 text-[11.5px] text-muted">range {price(range[0])} – {price(range[1])}</span>}
          </div>
          <div className="text-[11px] text-muted">Typical size for this kind of release; it does not say which way.</div>
        </div>
      )}
      {ev && p && (
        <div className="mt-2">
          <div className={LAB}>{live ? 'Chances' : 'Chances (advisory — not used for trades)'}</div>
          <div role="img" aria-label={`down ${pct(p.down)}, flat ${pct(p.side)}, up ${pct(p.up)}`} className="mt-1 flex h-2 gap-0.5">
            <span className="block rounded-sm bg-down" style={{ width: pct(p.down) }} />
            <span className="block rounded-sm bg-hover" style={{ width: pct(p.side) }} />
            <span className="block rounded-sm bg-up" style={{ width: pct(p.up) }} />
          </div>
          <div className="mt-0.5 flex justify-between text-[11.5px] tabular-nums text-muted">
            <span>down {pct(p.down)}</span><span>flat {pct(p.side)}</span><span>up {pct(p.up)}</span>
          </div>
          {extra.uncertain && <div className="text-[11.5px] text-warn">Close to even and uncertain: not a trade signal.</div>}
        </div>
      )}
      {ev && extra.phase === 'post' && extra.surprise_z != null && (
        <div className="mt-2 text-[12px]">
          <span className={LAB}>Surprise </span><span className="tabular-nums">{sgn(extra.surprise_z)}</span>{' '}
          <span className="text-muted">(standard deviations)</span>
        </div>
      )}
      {m5 && (m5.text || m5.bos) && (
        <div className="mt-2 flex flex-wrap gap-1.5 text-[11.5px]">
          {m5.bos && <span className="rounded bg-panel2 px-1.5 py-0.5">M5 break: {m5.bos}</span>}
          {m5.retest && <span className="rounded bg-panel2 px-1.5 py-0.5">retest: {m5.retest}</span>}
          {m5.text && <span className="rounded bg-panel2 px-1.5 py-0.5">{m5.text}</span>}
        </div>
      )}
      {extra.note && <p className="mt-2 text-[12.5px] leading-[1.45]">{extra.note}</p>}
      {!compact && sim.length > 0 && (
        <div className="mt-2.5 overflow-x-auto">
          <div className={LAB}>Similar past releases</div>
          <table className="mt-1 w-full text-[12px] tabular-nums">
            <thead>
              <tr className="text-left text-muted">
                <th className="font-normal">Date</th><th className="font-normal">Kind</th><th className="font-normal">Surprise</th>
                <th className="text-right font-normal">Move after 60 min</th>
              </tr>
            </thead>
            <tbody>
              {sim.map((s, i) => (
                <tr key={i} data-testid="similar-row" className="border-t border-line">
                  <td>{s.date ?? (s.t ? new Date(s.t * 1000).toISOString().slice(0, 10) : '—')}</td>
                  <td>{s.kind}</td>
                  <td>{sgn(s.z)}</td>
                  <td className={`text-right ${s.move60 > 0 ? 'text-up' : s.move60 < 0 ? 'text-down' : ''}`}>{money(s.move60)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!compact && extra.notes?.length > 0 && (
        <ul className="mt-2 list-disc pl-4 text-[11.5px] text-muted">{extra.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>
      )}
    </section>
  )
}

/** The news_intel agent row of an analysis, as card props. */
export function newsIntelProps(agents: { agent: string; bias_label: string; extra?: Record<string, unknown> }[]) {
  const r = agents.find((a) => a.agent === 'news_intel')
  return { extra: r?.extra as Extra, avoid: r?.bias_label === 'AVOID' }
}
