import type { Analysis } from '../../api/types'
import { price } from '../../lib/format'
import { Card, Meta, Sect, segCls } from '../journal/ui'
import { levelRows, type LevelRow } from './logic'

const KIND = {
  entry: 'bg-acc-bg text-[#5b8cff]', stop: 'bg-down-bg text-down', target: 'bg-up-bg text-up', pool: 'bg-warn-bg text-warn', other: 'bg-panel2 text-muted',
} as const
const Kind = ({ k, children }: { k: keyof typeof KIND; children: string }) =>
  <span className={`whitespace-nowrap rounded px-1.5 py-px text-[10.5px] font-bold uppercase ${KIND[k]}`}>{children}</span>

/** Old Levels tab: every price level from the plan, stop map and agents, highest first, with the current price marked. */
export default function LevelsPanel({ d, mode, onMode }: { d: Analysis; mode: 'day' | 'all'; onMode: (m: 'day' | 'all') => void }) {
  const c = d.chief, p = c.price, rng = c.day_range
  const { rows, total, day } = levelRows(c, d.agents, p, mode)
  const nowIdx = p == null ? -1 : rows.findIndex((r) => r.price < p)
  const dist = (r: LevelRow) => (p != null ? `${r.price >= p ? '+' : '−'}${price(Math.abs(r.price - p))}` : '')
  const nowRow = <tr key="now" className="bg-acc-bg text-accent"><td className="px-1.5 py-1 font-semibold tabular-nums">{price(p)}</td><td colSpan={3} className="px-1.5 py-1">◀ current price</td></tr>
  return (
    <div className="flex flex-col gap-2 pt-2">
      <div role="group" aria-label="Level range" className="flex gap-1.5">
        <button type="button" aria-pressed={day} className={segCls(day)} onClick={() => onMode('day')}>Today (±${rng ? Math.round(rng) : '—'})</button>
        <button type="button" aria-pressed={!day} className={segCls(!day)} onClick={() => onMode('all')}>All levels</button>
      </div>
      <Card label="Levels">
        <Sect>{day ? `Levels for today · within one average day's move ($${Math.round(rng)})` : 'All levels'} · highest first · distance from price</Sect>
        <div className="overflow-x-auto">
          <table aria-label="Levels" className="w-full border-collapse text-[12.5px]">
            <tbody>
              {rows.flatMap((r, i) => [
                ...(i === nowIdx ? [nowRow] : []),
                <tr key={i} className="border-t border-line align-top">
                  <td className="px-1.5 py-1.5 font-semibold tabular-nums">{price(r.price)}</td>
                  <td className="px-1.5 py-1.5"><Kind k={r.kcls}>{r.kind}</Kind></td>
                  <td className="px-1.5 py-1.5"><b>{r.src}</b> <span className="text-[11.5px] text-muted">{r.note}</span></td>
                  <td className="whitespace-nowrap px-1.5 py-1.5 text-right tabular-nums text-muted">{dist(r)}</td>
                </tr>,
              ])}
              {nowIdx === -1 && p != null && nowRow}
              {!rows.length && <tr><td className="text-[11.5px] text-muted">No levels yet.</td></tr>}
            </tbody>
          </table>
        </div>
        {day && total > rows.length && (
          <Meta cls="mt-1.5">{total - rows.length} far-away levels hidden (swing and weekly levels price is unlikely to reach today). Tap <b>All levels</b> to see them.</Meta>
        )}
      </Card>
      <Card label="How to read it">
        <Sect>How to read it</Sect>
        {([
          [<Kind key="a" k="pool">BUY STOPS</Kind>, 'Stop losses of sellers sit just above. Price is often pulled up to grab them, then can turn down.'],
          [<Kind key="b" k="pool">SELL STOPS</Kind>, 'Stop losses of buyers sit just below. Often swept before a move up.'],
          [<Kind key="c" k="pool">HUNTED</Kind>, 'Those stops were already taken. Less magnetic now.'],
          [<Kind key="d" k="other">RESISTANCE / SUPPORT</Kind>, 'Where price turned before. Expect a reaction, not a certain turn.'],
          [<span key="e" className="flex flex-wrap gap-1"><Kind k="entry">ENTRY</Kind><Kind k="stop">STOP</Kind><Kind k="target">TARGET</Kind></span>,
            "A trade idea's levels. Only \"Chief plan\" levels are AuEdge's actual call; others are one agent's view."],
          ['+ / − number', 'How far the level is above (+) or below (−) the current price, in dollars.'],
        ] as [React.ReactNode, string][]).map(([k, v], i) => (
          <div key={i} className="flex justify-between gap-3 border-b border-dashed border-line py-1.5 text-[12.5px] last:border-b-0">
            <span className="shrink-0 text-muted">{k}</span><span className="text-right">{v}</span>
          </div>
        ))}
      </Card>
    </div>
  )
}
