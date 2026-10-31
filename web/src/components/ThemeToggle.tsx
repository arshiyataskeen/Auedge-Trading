import { useState } from 'react'

export default function ThemeToggle() {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => (document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'))
  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    document.documentElement.dataset.theme = next
    try { localStorage.setItem('theme', next) } catch { /* storage blocked */ }
    setTheme(next)
  }
  return (
    <button type="button" onClick={toggle} aria-label="Toggle theme" title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      className="grid h-8 w-8 place-items-center rounded text-muted hover:bg-hover hover:text-strong">
      <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] fill-none stroke-current" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        {theme === 'dark'
          ? <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
          : <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>}
      </svg>
    </button>
  )
}
