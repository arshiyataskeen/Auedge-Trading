import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import LoadingCard from './LoadingCard'

type Props<T> = { query: UseQueryResult<T>; title?: string; children: (data: T) => ReactNode }

/** Loading placeholder (fixed min height) → inline error with Retry → children(data). */
export default function QueryCard<T>({ query, title, children }: Props<T>) {
  if (query.data === undefined) {
    if (query.isError) {
      return (
        <section className="rounded border border-line bg-panel p-3" style={{ minHeight: 120 }}>
          {title && <h3 className="mb-2 text-[12px] font-semibold text-strong">{title}</h3>}
          <div role="alert" className="flex items-center gap-3 text-[12px] text-down">
            <span>{title ? `${title}: ` : ''}{(query.error as Error).message}</span>
            <button type="button" disabled={query.isFetching} onClick={() => query.refetch()}
              className="rounded border border-line px-2 py-0.5 text-strong hover:bg-panel2 disabled:opacity-60">
              {query.isFetching ? 'Retrying…' : 'Retry'}
            </button>
          </div>
        </section>
      )
    }
    return <LoadingCard />
  }
  return <>{children(query.data)}</>
}
