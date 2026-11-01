import type { Quality } from '../api/types'
import { Card, Sect } from '../pages/journal/ui'

const BAND = { strong: 'text-up', good: 'text-up', fair: 'text-warn', weak: 'text-down' } as Record<string, string>

/** Setup quality: a 0-100 checklist score (not a chance of winning), its band, each factor with a plain reason, AVOID badge. */
export default function QualityCard({ q }: { q?: Quality | null }) {
  if (!q || !q.factors?.length) return null
  return (
    <Card label="Setup quality">
      <Sect>Setup quality</Sect>
      <div className="mb-1.5 flex flex-wrap items-baseline gap-2">
        <b className={`text-[20px] tabular-nums ${BAND[q.band] || 'text-text'}`}>{q.score}/100</b>
        <span className="text-[12.5px] text-muted">{q.band}</span>
        {q.avoid && <span className="rounded bg-down-bg px-1.5 py-px text-[11.5px] font-bold text-down">AVOID</span>}
      </div>
      {q.avoid && q.avoid_reasons.length > 0 && (
        <div className="mb-1.5 text-[12.5px] text-down">{q.avoid_reasons.join(' ')}</div>
      )}
      <ul className="flex flex-col gap-1 text-[12.5px]">
        {q.factors.filter((f) => f.weight > 0 || f.ok !== null).map((f) => (
          <li key={f.name} className="flex min-w-0 gap-1.5">
            <span aria-label={f.ok === true ? 'yes' : f.ok === false ? 'no' : 'not available'}
              className={`flex-none font-bold ${f.ok === true ? 'text-up' : f.ok === false ? 'text-down' : 'text-muted'}`}>
              {f.ok === true ? '✓' : f.ok === false ? '✗' : '–'}
            </span>
            <span className="min-w-0 break-words"><b>{f.label}</b>: <span className="text-muted">{f.text}</span></span>
          </li>
        ))}
      </ul>
      <div className="mt-1.5 text-[11px] text-muted">A checklist score, not a chance of winning.
        {q.flags_on && q.flags_on.length ? ` Filters on: ${q.flags_on.join(', ')}.` : ' Filters off: display only.'}</div>
    </Card>
  )
}
