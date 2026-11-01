import type { ReactNode } from 'react'

export type SummaryItem = { label: string; value: ReactNode }

export default function SummaryCard({ title, items }: { title?: string; items: SummaryItem[] }) {
  return (
    <section className="rounded border border-line bg-panel p-3">
      {title && <h3 className="mb-2 text-[12px] font-semibold text-strong">{title}</h3>}
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-[12px]">
        {items.map((it) => (
          <div key={it.label} className="contents">
            <dt className="text-muted">{it.label}</dt>
            <dd className="text-right tabular-nums text-strong">{it.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
