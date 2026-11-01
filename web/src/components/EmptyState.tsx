import type { ReactNode } from 'react'

export default function EmptyState({ children }: { children: ReactNode }) {
  return <div className="rounded border border-dashed border-line p-4 text-center text-[12px] text-muted">{children}</div>
}
