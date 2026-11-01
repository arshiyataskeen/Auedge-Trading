import type { BacktestStatus } from '../../api/types'
import { pctOf } from './ui'

/** Progress of the running backtest / health check (phase, percent, elapsed time). */
export default function ProgressBar({ status, label }: { status: BacktestStatus; label?: string }) {
  const pct = pctOf(status.progress)
  const el = status.elapsed ?? 0
  return (
    <div className="mt-3">
      <div role="progressbar" aria-label={label ?? 'Progress'} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
        className="h-2 overflow-hidden rounded bg-panel2">
        <div className="h-full bg-accent transition-[width]" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 text-[11.5px] text-muted">
        {label ? `${label} · ` : ''}{status.progress?.phase || 'Starting'} · {pct}% · {Math.floor(el / 60)}m {el % 60}s
      </div>
    </div>
  )
}
