import { useEffect, useState } from 'react'

export type Theme = 'dark' | 'light'
const current = (): Theme => (document.documentElement.dataset.theme === 'light' ? 'light' : 'dark')

/** The page theme (ThemeToggle sets data-theme on <html>); charts re-read their colours when it changes. */
export function useTheme(): Theme {
  const [t, setT] = useState<Theme>(current)
  useEffect(() => {
    const mo = new MutationObserver(() => setT(current()))
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => mo.disconnect()
  }, [])
  return t
}
