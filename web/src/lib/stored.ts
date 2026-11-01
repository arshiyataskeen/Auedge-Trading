import { useSyncExternalStore } from 'react'

/* localStorage as a store (same keys as the old page; shared across components) */

const subs = new Set<() => void>()
function read(key: string): string | null { try { return localStorage.getItem(key) } catch { return null } }
export function writeStored(key: string, v: string) {
  try { localStorage.setItem(key, v) } catch { /* storage blocked: the change is lost on reload */ }
  subs.forEach((f) => f())
}
export const readStored = (key: string, def: string) => read(key) ?? def
/** Raw string stored under `key`, re-rendering on every write made through writeStored. */
export function useStored(key: string, def: string): [string, (v: string) => void] {
  const raw = useSyncExternalStore((cb) => { subs.add(cb); return () => { subs.delete(cb) } }, () => read(key))
  return [raw ?? def, (v) => writeStored(key, v)]
}
