import type { ReactNode } from 'react'

export default function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="text-[16px] font-semibold text-strong">{title}</h1>
        {subtitle != null && <div className="text-[12px] text-muted">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
