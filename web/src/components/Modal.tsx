import { useEffect, useRef, type ReactNode } from 'react'

/** Dialog with focus trap, Escape to close, backdrop click to close; focus returns to the opener. Same behaviour as TradeReplay / DayReplay. */
export default function Modal({ label, onClose, children, width = 760 }: { label: string; onClose: () => void; children: ReactNode; width?: number }) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    return () => prev?.focus?.()
  }, [])
  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === 'Escape') { e.stopPropagation(); onCloseRef.current(); return }
      if (e.key !== 'Tab') return
      const dlg = dialogRef.current
      if (!dlg) return
      const f = [...dlg.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select, textarea, [href], [tabindex]:not([tabindex="-1"])')]
      if (!f.length) return
      const first = f[0], last = f[f.length - 1], a = document.activeElement
      const inside = !!a && dlg.contains(a)
      if (e.shiftKey && (a === first || !inside)) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && (a === last || !inside)) { e.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1} style={{ width: `min(${width}px, 96vw)` }}
        className="relative max-h-[94vh] overflow-y-auto rounded-md border border-line2 bg-panel2 p-4 text-text">
        <button ref={closeRef} type="button" aria-label="Close" onClick={onClose}
          className="absolute right-2 top-2 h-8 w-8 rounded text-[18px] text-muted hover:bg-hover">×</button>
        {children}
      </div>
    </div>
  )
}
