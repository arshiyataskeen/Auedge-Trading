const W = 420, H = 130, PAD = 6

/** Port of the old equitySvg: cumulative result line starting at 0; `curve` is [time, cumulative][]. */
export default function EquityChart({ curve, unit = 'R' }: { curve: [number, number][]; unit?: 'R' | '$' }) {
  if (!curve.length) return null
  const ys = [0, ...curve.map((p) => p[1])]
  const lo = Math.min(...ys), hi = Math.max(...ys), span = hi - lo || 1
  const x = (i: number) => PAD + (W - 2 * PAD) * (i / Math.max(1, curve.length))
  const y = (v: number) => PAD + (H - 2 * PAD) * (1 - (v - lo) / span)
  const pts = [[x(0), y(0)], ...curve.map((p, i) => [x(i + 1), y(p[1])])]
    .map((p) => p.map((v) => v.toFixed(1)).join(',')).join(' ')
  const col = curve[curve.length - 1][1] >= 0 ? 'var(--up)' : 'var(--down)'
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`Equity curve in ${unit}`}
        className="h-[130px] w-full">
        <line x1="0" x2={W} y1={y(0)} y2={y(0)} stroke="var(--line2)" strokeDasharray="4 4" />
        <polyline points={pts} fill="none" stroke={col} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="flex justify-between text-[11px] text-muted">
        <span>Start ({unit === '$' ? '$0' : '0R'})</span>
        <span>{curve.length} trades · cumulative result {unit === '$' ? 'in dollars' : 'in R'}</span>
      </div>
    </div>
  )
}
