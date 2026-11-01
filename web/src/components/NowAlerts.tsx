import { createContext, useContext, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Analysis } from '../api/types'
import { price } from '../lib/format'
import { readStored, useStored, writeStored } from '../lib/stored'
import { Bias } from '../pages/dashboard/Cards'

let ctx: AudioContext | null = null
/** Old beep(): three rising tones. Silent where audio is blocked or missing. */
export function beep() {
  try {
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    ctx = ctx || new AC()
    const t0 = ctx.currentTime
    for (const [f, dt] of [[880, 0], [1175, 0.18], [1568, 0.36]]) {
      const o = ctx.createOscillator(), g = ctx.createGain()
      o.frequency.value = f; o.type = 'sine'; o.connect(g); g.connect(ctx.destination)
      g.gain.setValueAtTime(0.0001, t0 + dt); g.gain.exponentialRampToValueAtTime(0.25, t0 + dt + 0.02)
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + 0.16); o.start(t0 + dt); o.stop(t0 + dt + 0.17)
    }
  } catch { /* no audio */ }
}

export type Toast = { id: number; side: 'BUY' | 'SELL'; test: boolean; text: string }
const SAME_PLAN_MS = 2 * 3600e3

/**
 * Old nowAlert(): on a NOW plan (or a test) beep, return the pop-up and, when allowed and the tab is hidden, show a system notification.
 * The same plan (side + rounded entry) alerts once per 2 hours; the last one is remembered in localStorage ("lastAlert").
 */
export function nowAlert(d: Analysis | null, test = false, nowMs = Date.now()): Toast | null {
  const plan = d?.chief?.plan
  if (!test && (!plan || plan.kind !== 'now' || plan.entry_lo == null || plan.entry_hi == null)) return null
  const mid = plan && plan.entry_lo != null && plan.entry_hi != null ? (plan.entry_lo + plan.entry_hi) / 2 : 0
  const key = test ? 'test' : `${plan!.side}|${Math.round(mid)}`
  if (!test) {
    let last: { key?: string; at?: number } = {}
    try { last = JSON.parse(readStored('lastAlert', '{}')) } catch { /* none */ }
    if (last.key === key && nowMs - (last.at ?? 0) < SAME_PLAN_MS) return null
    writeStored('lastAlert', JSON.stringify({ key, at: nowMs }))
  }
  const side = test ? 'BUY' : (plan!.side ?? 'BUY')
  const text = test ? "Alerts are on. You'll hear this when AuEdge says BUY NOW or SELL NOW."
    : `${side} NOW near ${price(mid)} · stop ${price(plan!.stop)} · half at ${price(plan!.be_at)} · target ${price(plan!.t1)}`
  beep()
  try {
    if (!test && 'Notification' in window && Notification.permission === 'granted' && document.hidden)
      new Notification(`AuEdge: ${side} NOW`, { body: text, icon: '/icon-192.png', tag: 'auedge-now' })
  } catch { /* notifications unavailable */ }
  return { id: nowMs, side, test, text }
}

/** Alerts on/off (persisted as "alerts"), raising a pop-up for each new NOW call in `d`. */
export function useNowAlerts(d: Analysis | undefined) {
  const [raw, set] = useStored('alerts', '0')
  const on = raw === '1'
  const [toast, setToast] = useState<Toast | null>(null)
  useEffect(() => { // every new analysis (and switching alerts on) is checked; nowAlert itself skips an unchanged plan
    if (!on || !d) return
    const t = nowAlert(d)
    if (t) setToast(t)
  }, [on, d])
  useEffect(() => {
    if (!toast) return
    const id = setTimeout(() => setToast(null), 60000)
    return () => clearTimeout(id)
  }, [toast])
  const toggle = async () => {
    if (on) { set('0'); return }
    try { if ('Notification' in window && Notification.permission === 'default') await Notification.requestPermission() } catch { /* ignore */ }
    setToast(nowAlert(null, true)) // old order: the test pop-up first, then a real NOW call (set below) replaces it
    set('1')
  }
  return { on, toggle, toast, dismiss: () => setToast(null) }
}

export type NowAlerts = ReturnType<typeof useNowAlerts>
const OFF: NowAlerts = { on: false, toggle: async () => {}, toast: null, dismiss: () => {} }
/** Alerts are owned by the app shell (they must work on every page); the top bar's bell reads them from here. */
export const NowAlertsContext = createContext<NowAlerts>(OFF)
export const useAlertsContext = () => useContext(NowAlertsContext)

export function AlertButton({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button type="button" aria-pressed={on} aria-label="Alerts for BUY NOW / SELL NOW" onClick={onClick}
      title={on ? 'Alerts ON: sound and pop-up for BUY NOW / SELL NOW. Click to turn off.'
        : 'Alerts OFF. Click for a sound and pop-up when AuEdge says BUY NOW or SELL NOW.'}
      className={`grid h-8 w-8 place-items-center rounded border ${on ? 'border-accent bg-acc-bg text-strong' : 'border-line text-muted hover:bg-hover'}`}>
      <svg viewBox="0 0 24 24" className="h-[17px] w-[17px] fill-none stroke-current" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z" /><path d="M10 20.5a2 2 0 0 0 4 0" />
      </svg>
    </button>
  )
}

/** The pop-up (old .nowtoast): click it to go to the plan, ✕ to close. */
export function NowToast({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  return (
    <div role="alert"
      className="fixed left-1/2 top-14 z-[60] flex max-w-[94vw] -translate-x-1/2 items-center gap-3 rounded-md border border-line2 bg-panel2 px-3 py-2 shadow-lg">
      <Bias kind={toast.side}>{toast.test ? 'TEST' : `${toast.side} NOW`}</Bias>
      <div className="min-w-0 text-[12px]">
        <b className="block text-[14px] text-strong">{toast.test ? 'Alerts on' : 'AuEdge trade call'}</b>
        <span className="text-muted">{toast.text}</span>
        {!toast.test && <Link to="/trade" onClick={onClose} className="ml-2 text-accent underline">Open plan</Link>}
      </div>
      <button type="button" aria-label="Close alert" onClick={onClose} className="h-7 w-7 shrink-0 rounded text-[16px] text-muted hover:bg-hover">✕</button>
    </div>
  )
}
