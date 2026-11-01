import type { ReactNode } from 'react'

/** Title row. `middle` (optional) sits between the title and the actions; under 1100 px it wraps onto its own line below the title. */
export default function PageHeader({ title, subtitle, actions, middle }: { title: string; subtitle?: ReactNode; actions?: ReactNode; middle?: ReactNode }) {
  return (
    <div data-testid="page-header" className={`mb-3 flex flex-wrap items-center gap-x-3 gap-y-2 ${middle ? '' : 'justify-between'}`}>
      <div>
        <h1 className="text-[16px] font-semibold text-strong">{title}</h1>
        {subtitle != null && <div className="text-[12px] text-muted">{subtitle}</div>}
      </div>
      {middle && <div className="order-last flex min-w-0 basis-full flex-wrap items-center gap-2 min-[1100px]:order-none min-[1100px]:basis-0 min-[1100px]:flex-1">{middle}</div>}
      {actions && <div className={`flex flex-wrap items-center gap-2 ${middle ? 'ml-auto' : ''}`}>{actions}</div>}
    </div>
  )
}
