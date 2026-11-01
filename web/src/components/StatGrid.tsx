import type { ReactNode } from 'react'

export type Stat = { label: string; value: ReactNode; sub?: ReactNode }

export default function StatGrid({ stats }: { stats: Stat[] }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(120px,1fr))] gap-2">
      {stats.map((s) => (
        <div key={s.label} className="rounded border border-line bg-panel p-2">
          <div className="text-[10px] uppercase text-muted">{s.label}</div>
          <div className="text-[16px] font-semibold tabular-nums text-strong">{s.value}</div>
          {s.sub != null && <div className="text-[11px] tabular-nums text-muted">{s.sub}</div>}
        </div>
      ))}
    </div>
  )
}
