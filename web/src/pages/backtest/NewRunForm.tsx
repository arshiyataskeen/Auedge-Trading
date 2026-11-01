import { useEffect, useState } from 'react'
import { useRunBacktest } from '../../api/endpoints'
import type { BacktestInfo, BacktestStatus, RunBody } from '../../api/types'
import ProgressBar from './ProgressBar'
import { btn, btnOn, card, field, lsGet, lsSet, sect, ymd } from './ui'

type Props = { info: BacktestInfo; status?: BacktestStatus; running: boolean }

const PRESETS = [[7, 'Last week'], [30, 'Last month'], [91, '3 months'], [183, '6 months']] as const
const lab = 'flex items-center gap-1.5 text-[12.5px] text-text'
const flag = (k: string, d: string) => lsGet(k, d) === '1'
const row = 'mb-3 flex flex-wrap items-center gap-x-4 gap-y-2'

/** Port of renderBacktestTab's form + btPreset / btEstimate / btLimits and the old "Run backtest" click handler. */
export default function NewRunForm({ info, status, running }: Props) {
  const run = useRunBacktest()
  const r = info.range
  const cached = !!r && r.cached

  const [step, setStep] = useState('auto')
  const lim = cached ? { min: ymd(step === '15m' ? r.first_15m : r.first_1h), max: ymd(r.last) } : null
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [preset, setPreset] = useState<number | null>(null)
  const [spread, setSpread] = useState('0.30')
  const [acct, setAcct] = useState(() => lsGet('btAcct', '25000'))
  const [lot, setLot] = useState(() => lsGet('btLot', '0.1'))
  const [rr, setRR] = useState(() => lsGet('btRR', ''))
  const [half, setHalf] = useState(() => flag('btHalf', '1'))
  const [dayLoss, setDayLoss] = useState(() => lsGet('btDayLoss', '350'))
  const [dayProfit, setDayProfit] = useState(() => lsGet('btDayProfit', '150'))
  const [adapt, setAdapt] = useState(() => flag('btAdapt', '0'))
  const [live, setLive] = useState(() => flag('btLive', '1'))
  const [harsh, setHarsh] = useState(() => flag('btHarsh', '0'))
  const [fSess, setFSess] = useState(() => flag('btFSess', '0'))
  const [fTrend, setFTrend] = useState(() => flag('btFTrend', '0'))
  const [fHunt, setFHunt] = useState(() => flag('btFHunt', '0'))

  const applyPreset = (days: number) => {
    if (!lim) return
    const t = Date.parse(lim.max)
    const f = Math.max(Date.parse(lim.min), t - (days - 1) * 864e5)
    setFrom(ymd(f / 1000)); setTo(lim.max); setPreset(days)
  }
  // Old behaviour: the form opens on "Last month".
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { applyPreset(30) }, [cached, r?.last])

  const changeStep = (v: string) => {
    setStep(v); setPreset(null)
    if (!cached) return
    const min = ymd(v === '15m' ? r.first_15m : r.first_1h)
    if (from < min) setFrom(min)
  }

  let hint = ''
  if (lim && from && to) {
    const days = (Date.parse(to) - Date.parse(from)) / 864e5 + 1
    const eff = step === 'auto' ? (Date.parse(from) / 1000 >= r.first_15m && days <= 45 ? '15m' : '1h') : step
    const sec = Math.round(15 + days * (eff === '15m' ? 2.5 : 2))
    hint = `${Math.max(0, Math.round(days))} days · steps every ${eff === '15m' ? '15 minutes (precise)' : 'hour (1H stands in for 15m before the last month)'} · roughly ${sec < 90 ? sec + ' s' : Math.round(sec / 60) + ' min'}.`
  }

  const start = () => {
    const rrv = rr.trim()
    const body: RunBody = {
      start: from, end: to, step, spread: +spread, account: +acct, lot: +lot, target_rr: rrv ? +rrv : null, partial: half,
      adaptive: adapt, day_max_loss: +dayLoss || 0, day_max_profit: +dayProfit || 0, live_rules: live,
      f_session: fSess, f_trend: fTrend, f_hunt: fHunt,
    }
    if (harsh) { body.spread *= 2; body.stop_slip = 0.5 }
    lsSet('btAcct', acct); lsSet('btLot', lot); lsSet('btRR', rrv); lsSet('btHalf', half ? '1' : '0')
    lsSet('btDayLoss', dayLoss); lsSet('btDayProfit', dayProfit); lsSet('btAdapt', adapt ? '1' : '0')
    lsSet('btLive', live ? '1' : '0'); lsSet('btHarsh', harsh ? '1' : '0')
    lsSet('btFSess', fSess ? '1' : '0'); lsSet('btFTrend', fTrend ? '1' : '0'); lsSet('btFHunt', fHunt ? '1' : '0')
    run.mutate(body)
  }

  const cb = (label: string, v: boolean, set: (b: boolean) => void, title?: string) => (
    <label className={lab} title={title}><input type="checkbox" checked={v} onChange={(e) => set(e.target.checked)} /> {label}</label>
  )
  const num = (label: string, v: string, set: (s: string) => void, props: React.InputHTMLAttributes<HTMLInputElement>, title?: string) => (
    <label className={lab} title={title}>{label}
      <input type="number" className={`${field} w-24`} value={v} onChange={(e) => set(e.target.value)} {...props} />
    </label>
  )

  return (
    <section className={`${card} mb-3`} aria-label="New backtest">
      <h2 className={sect}>Choose a period to test</h2>
      {!lim ? (
        <div role="alert" className="text-[12.5px] text-warn">
          No downloaded history yet. Run <b>backtest.py</b> once (see README_backtest.md), then reopen this page.
        </div>
      ) : (
        <>
          <div className={row}>
            {PRESETS.map(([d, l]) => (
              <button key={d} type="button" aria-pressed={preset === d} className={preset === d ? btnOn : btn} onClick={() => applyPreset(d)}>{l}</button>
            ))}
          </div>
          <div className={row}>
            <label className={lab}>From <input type="date" className={field} min={lim.min} max={lim.max} value={from}
              onChange={(e) => { setFrom(e.target.value); setPreset(null) }} /></label>
            <label className={lab}>To <input type="date" className={field} min={lim.min} max={lim.max} value={to}
              onChange={(e) => { setTo(e.target.value); setPreset(null) }} /></label>
            <label className={lab}>Steps
              <select className={field} value={step} onChange={(e) => changeStep(e.target.value)}>
                <option value="auto">Auto (best for the period)</option>
                <option value="15m">Every 15 min · precise · last ~month only</option>
                <option value="1h">Every hour · faster · up to 6 months</option>
              </select></label>
            {num('Cost per side $', spread, setSpread, { min: 0, max: 5, step: 0.05 })}
          </div>
          <div className={row}>
            {num('Account $', acct, setAcct, { min: 100, step: 1000 })}
            {num('Lot', lot, setLot, { min: 0.01, step: 0.01 })}
            {num('Target R:R', rr, setRR, { min: 0.5, max: 10, step: 0.05, placeholder: "plan's" })}
            {cb('Half off at 1R', half, setHalf)}
            {num('Day loss limit $', dayLoss, setDayLoss, { min: 0, step: 50 }, "Stop new trades for the day once the day's result reaches this loss (0 = off)")}
            {num('Day profit target $', dayProfit, setDayProfit, { min: 0, step: 50 }, "Stop new trades for the day once the day's result reaches this profit (0 = off)")}
            {cb('Performance weights', adapt, setAdapt, "Weekly vote weights from each agent's past results (walk-forward: only data known before each week)")}
          </div>
          <div className={row}>
            <b className="text-[12.5px] text-text">Rules</b>
            {cb('Live discipline rules', live, setLive, "Same as live: stop after 2 losing trades in a day, wait 60 minutes after a loss, don't chase a big 1-hour move")}
            {cb('Harsh costs', harsh, setHarsh, 'Stress test: double the cost per side and lose an extra $0.50 every time a stop fills (real fills are often worse)')}
          </div>
          <div className={row}>
            <b className="text-[12.5px] text-text">Quality filters</b><span className="text-[11.5px] text-muted">(experiments, off in live)</span>
            {cb('London / NY hours only', fSess, setFSess, 'Only open trades between 07:00 London and 12:00 New York, the busiest hours')}
            {cb('Daily + 4H agree', fTrend, setFTrend, "Only trade when the Daily and 4H trends both point the trade's way")}
            {cb('After a stop hunt only', fHunt, setFHunt, 'Only trade right after stops on the other side were hunted')}
          </div>
          <p className="mb-3 min-h-[1.2em] text-[11.5px] text-muted">{hint}</p>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className="rounded bg-accent px-4 py-1.5 text-[12.5px] font-semibold text-white disabled:opacity-50"
              disabled={running || run.isPending || !from || !to} onClick={start}>Run backtest</button>
            <span className="text-[11.5px] text-muted">Data available {lim.min} to {lim.max}</span>
          </div>
          {run.isError && <div role="alert" className="mt-2 text-[12.5px] text-warn">{(run.error as Error).message}</div>}
          {running && status && !String(status.id ?? '').startsWith('hc_') && <ProgressBar status={status} />}
        </>
      )}
    </section>
  )
}
