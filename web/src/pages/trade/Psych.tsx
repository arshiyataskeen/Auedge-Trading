import type { AgentView, TradePlan } from '../../api/types'
import { Meta, Sect } from '../journal/ui'
import { CHECKS, MY_MAX_LOSSES, MY_MAX_TRADES, parseChecks, parseMyDay, useStored, writeStored, type MyDay } from './logic'

/** The "my trades today" counters kept in this browser (old myDay()); `myStop` = the daily limit is reached. */
export function useMyDay(): { my: MyDay; myStop: boolean } {
  const [raw] = useStored('myDay', '{}')
  const my = parseMyDay(raw)
  return { my, myStop: my.trades >= MY_MAX_TRADES || my.losses >= MY_MAX_LOSSES }
}

type Key = 'trades' | 'losses'
function Step({ k, val, label, max, onStep }: { k: Key; val: number; label: string; max: number; onStep: (k: Key, d: number) => void }) {
  const btn = 'h-9 w-9 rounded border border-line bg-panel2 text-[16px] font-bold text-strong hover:bg-hover min-[900px]:h-7 min-[900px]:w-7'
  return (
    <span className="mr-4 inline-flex items-center gap-1.5">
      <span className="text-muted">{label}</span>
      <button type="button" aria-label={`Less ${k}`} className={btn} onClick={() => onStep(k, -1)}>−</button>
      <b className={`min-w-4 text-center text-[15px] ${val >= max ? 'text-warn' : ''}`}>{val}</b>
      <button type="button" aria-label={`More ${k}`} className={btn} onClick={() => onStep(k, 1)}>+</button>
      <span className="text-muted">/ {max}</span>
    </span>
  )
}

/** Old psychCard(): the discipline agent's warnings and rows, my own trade counters, and the four-point pre-trade checklist. */
export default function PsychCard({ psy, plan, genAt, userStop }: { psy: AgentView | undefined; plan: TradePlan; genAt: string; userStop: boolean }) {
  const { my } = useMyDay()
  const [rawChecks] = useStored('checks', '{}')
  const mine = parseChecks(rawChecks, genAt)
  const done = CHECKS.filter(([k]) => mine[k]).length
  const onStep = (k: Key, d: number) => {
    const v = { ...my, [k]: Math.max(0, my[k] + d) }
    if (v.losses > v.trades) v.trades = v.losses
    writeStored('myDay', JSON.stringify(v))
  }
  const onCheck = (k: string, on: boolean) => writeStored('checks', JSON.stringify({ ...mine, [k]: on }))
  const warns = psy?.warnings ?? []
  return (
    <section aria-label="Discipline coach" className="rounded border border-line bg-panel p-3">
      <Sect>Discipline coach · your own psychology before every trade</Sect>
      {warns.length ? <ul className="mb-2 ml-[18px] list-disc text-[13px] text-warn">{warns.map((w, i) => <li key={i}>{w}</li>)}</ul>
        : <div className="mb-2 rounded bg-up-bg px-2 py-1.5 text-[12.5px] font-semibold text-up">No discipline problems right now. Trade only the plan.</div>}
      {psy?.status === 'OK' && (
        <div>
          {psy.rows.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3 border-b border-dashed border-line py-1 text-[12.5px]">
              <span className="whitespace-nowrap text-muted">{k}</span><b className="text-right font-medium">{v}</b>
            </div>
          ))}
        </div>
      )}
      <div className="mt-2.5">
        <div className="mb-1.5 text-[12px] font-semibold text-strong">My trades today (the ones you really took)</div>
        <div className="flex flex-wrap items-center gap-y-1 text-[12.5px]">
          <Step k="trades" val={my.trades} label="Trades" max={MY_MAX_TRADES} onStep={onStep} />
          <Step k="losses" val={my.losses} label="Losses" max={MY_MAX_LOSSES} onStep={onStep} />
        </div>
        {userStop && <div className="mt-2 rounded bg-down-bg px-2.5 py-2 text-[13px] font-semibold text-down">Your daily limit is reached. Close the platform for today; tomorrow is a new day.</div>}
      </div>
      {plan.stop != null && !userStop && (
        <div className="mt-3">
          <div className="mb-1.5 text-[12px] font-semibold text-strong">Before you enter · {done}/{CHECKS.length} {done === CHECKS.length ? '· ready' : ''}</div>
          {CHECKS.map(([k, txt]) => (
            <label key={k} className="flex cursor-pointer items-start gap-2 py-1 text-[13px]">
              <input type="checkbox" checked={!!mine[k]} onChange={(e) => onCheck(k, e.target.checked)} className="mt-[3px] accent-up" /> {txt}
            </label>
          ))}
          {done === CHECKS.length
            ? <div className="mt-1 rounded bg-up-bg px-2 py-1.5 text-[12.5px] font-semibold text-up">All checked. Enter only inside the entry zone, stop first.</div>
            : <Meta cls="mt-1">Tick all four before entering. If you can't, skip this trade.</Meta>}
        </div>
      )}
    </section>
  )
}
