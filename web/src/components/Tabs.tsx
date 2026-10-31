import { Children, useRef, type KeyboardEvent, type ReactNode } from 'react'

type Item = { key: string; label: string }

/** Accessible tab strip. Children are the panels, in the same order as `items`; only the active one renders. */
export default function Tabs({ items, value, onChange, children, label }: {
  items: Item[]; value: string; onChange: (key: string) => void; children?: ReactNode; label?: string
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const idx = Math.max(0, items.findIndex((i) => i.key === value))
  const panels = Children.toArray(children)

  const onKey = (e: KeyboardEvent) => {
    const n = items.length
    let next = -1
    if (e.key === 'ArrowRight') next = (idx + 1) % n
    else if (e.key === 'ArrowLeft') next = (idx - 1 + n) % n
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = n - 1
    if (next < 0) return
    e.preventDefault()
    onChange(items[next].key)
    refs.current[next]?.focus()
  }

  return (
    <>
      <div role="tablist" aria-label={label} className="flex gap-1 border-b border-line" onKeyDown={onKey}>
        {items.map((it, i) => {
          const on = i === idx
          return (
            <button key={it.key} ref={(el) => { refs.current[i] = el }} role="tab" id={`tab-${it.key}`} type="button"
              aria-selected={on} aria-controls={`panel-${it.key}`} tabIndex={on ? 0 : -1} onClick={() => onChange(it.key)}
              className={`-mb-px border-b-2 px-3 py-2 text-[13px] ${on ? 'border-accent text-strong' : 'border-transparent text-muted hover:text-text'}`}>
              {it.label}
            </button>
          )
        })}
      </div>
      {panels[idx] !== undefined && (
        <div role="tabpanel" id={`panel-${items[idx].key}`} aria-labelledby={`tab-${items[idx].key}`}>{panels[idx]}</div>
      )}
    </>
  )
}
