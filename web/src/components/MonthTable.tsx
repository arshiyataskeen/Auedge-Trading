import type { Groups } from '../lib/periods'
import { sortedKeys } from '../lib/periods'
import { money } from '../lib/format'
import { monthName } from '../lib/time'
import BarCell from './BarCell'
import MoneyText from './MoneyText'

type Props = {
  groups: Groups
  year: string
  onPick: (month: string) => void
  onPickYear?: (year: string) => void
  selectedMonth?: string | null
}

const bal = (v: number | null) => (v != null ? money(v, { sign: false }) : '')

/** Port of btMonthsHtml: year chips (when several), a month table with a bar column, and the year total. */
export default function MonthTable({ groups, year, onPick, onPickYear, selectedMonth }: Props) {
  const r = !groups.hasUsd
  const years = sortedKeys(groups.years)
  const months = sortedKeys(groups.months).filter((k) => k.startsWith(year))
  const yx = groups.years.get(year)
  const maxAbs = Math.max(1, ...months.map((k) => Math.abs(groups.months.get(k)!.pnl)))
  return (
    <div>
      {years.length > 1 && (
        <div className="mb-2.5 grid grid-cols-[repeat(auto-fill,minmax(118px,1fr))] gap-1.5">
          {years.map((y) => {
            const x = groups.years.get(y)!
            return (
              <button key={y} type="button" aria-pressed={y === year} onClick={() => onPickYear?.(y)}
                className={`flex flex-col items-start rounded border px-2 py-1.5 text-left text-[12px] ${y === year ? 'border-accent bg-panel2' : 'border-line bg-bg'}`}>
                <b className="text-strong">{y}</b>
                <MoneyText v={x.pnl} r={r} />
                <span className="text-[11px] text-muted">{x.n} trades</span>
              </button>
            )
          })}
        </div>
      )}
      <table className="w-full text-[12.5px] tabular-nums">
        <thead>
          <tr className="text-left text-[11px] text-muted">
            <th className="py-1 font-normal">Month</th><th className="font-normal">Trades</th>
            <th className="font-normal">Won / lost</th><th className="text-right font-normal">Profit / loss</th>
            <th /><th className="text-right font-normal">Balance</th>
          </tr>
        </thead>
        <tbody>
          {months.map((k) => {
            const x = groups.months.get(k)!
            return (
              <tr key={k} data-month={k} onClick={() => onPick(k)}
                className={`cursor-pointer border-t border-line hover:bg-hover ${k === selectedMonth ? 'bg-hover' : ''}`}>
                <td className="py-[7px]">
                  <button type="button" aria-label={`Show days of ${monthName(k)}`}
                    onClick={(e) => { e.stopPropagation(); onPick(k) }} className="font-bold text-strong">{monthName(k)}</button>
                </td>
                <td>{x.n}</td><td>{x.won} / {x.lost}</td>
                <td className="text-right font-bold"><MoneyText v={x.pnl} r={r} /></td>
                <td className="w-[24%] px-2"><BarCell value={x.pnl} max={maxAbs} label={`${monthName(k)} result`} /></td>
                <td className="text-right text-[11px] text-muted">{bal(x.bal)}</td>
              </tr>
            )
          })}
          {yx && (
            <tr className="border-t-2 border-line2">
              <td className="py-[7px] font-bold text-strong">{year} total</td><td>{yx.n}</td><td>{yx.won} / {yx.lost}</td>
              <td className="text-right font-bold"><MoneyText v={yx.pnl} r={r} /></td><td />
              <td className="text-right text-[11px] text-muted">{bal(yx.bal)}</td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="mt-1.5 text-[11px] text-muted">
        {months.filter((k) => groups.months.get(k)!.pnl > 0).length} winning and{' '}
        {months.filter((k) => groups.months.get(k)!.pnl < 0).length} losing months in {year}.
      </p>
    </div>
  )
}
