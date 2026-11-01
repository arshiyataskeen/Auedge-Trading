/** Horizontal bar with a centred zero line for signed values; `value` is scaled against `max`. */
export default function BarCell({ value, max, label }: { value: number; max: number; label?: string }) {
  const pct = max > 0 ? Math.min(50, (Math.abs(value) / max) * 50) : 0
  const up = value >= 0
  return (
    <div role="img" aria-label={label ?? String(value)} className="relative h-2 w-full min-w-[60px] rounded bg-panel2">
      <div className="absolute inset-y-0 left-1/2 w-px bg-line2" />
      <div className={`absolute inset-y-0 rounded ${up ? 'bg-up' : 'bg-down'}`}
        style={up ? { left: '50%', width: `${pct}%` } : { right: '50%', width: `${pct}%` }} />
    </div>
  )
}
