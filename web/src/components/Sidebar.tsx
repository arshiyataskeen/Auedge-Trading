import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useNews } from '../api/endpoints'

const ICONS: Record<string, ReactNode> = {
  dashboard: <><path d="M4 11l8-7 8 7" /><path d="M6 10v10h12V10" /></>,
  trade: <><path d="M4 19V5M4 19h16" /><path d="M7 15l4-5 3 3 5-6" /></>,
  backtest: <><path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1" /><path d="M3 4v4.5h4.5" /><path d="M12 7.5V12l3 2" /></>,
  journal: <><path d="M9 4h6a1 1 0 0 1 1 1v1H8V5a1 1 0 0 1 1-1z" /><path d="M16 5h2a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h2" /><path d="M9 12l2 2 4-4" /></>,
  demo: <><rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18" /><path d="M16 14.5h2" /><path d="M7 6V4.5h10V6" /></>,
  news: <><rect x="3.5" y="5" width="17" height="15.5" rx="2" /><path d="M3.5 9.5h17M8 3v4M16 3v4" /><path d="M7.5 13.5h3M7.5 16.5h6" /></>,
  agents: <><circle cx="9" cy="8" r="3.2" /><path d="M3.5 19c.6-3 2.8-4.6 5.5-4.6s4.9 1.6 5.5 4.6" /><circle cx="17" cy="9" r="2.5" /><path d="M16 14.6c2.3.1 3.9 1.5 4.5 4.4" /></>,
}

export const NAV_ITEMS = [
  { to: '/dashboard', key: 'dashboard', label: 'Dashboard' },
  { to: '/trade', key: 'trade', label: 'Trade' },
  { to: '/backtest', key: 'backtest', label: 'Backtest' },
  { to: '/journal', key: 'journal', label: 'Journal' },
  { to: '/demo', key: 'demo', label: 'Demo' },
  { to: '/news', key: 'news', label: 'News' },
  { to: '/agents', key: 'agents', label: 'Agents' },
]

/** Left rail on desktop; fixed bottom bar under 768 px. */
export default function Sidebar() {
  const news = useNews()
  const now = Date.now() / 1000   // old renderNews: High-impact events due within the next 24 h
  const soon = (news.data?.events ?? []).filter((e) => e.impact === 'High' && e.t > now && e.t - now < 86400).length
  return (
    <nav aria-label="Main"
      className="z-20 flex shrink-0 flex-col items-stretch gap-1 border-r border-line bg-app p-1.5 max-md:fixed max-md:inset-x-0 max-md:bottom-0 max-md:flex-row max-md:justify-around max-md:border-r-0 max-md:border-t md:w-[68px]">
      {NAV_ITEMS.map((it) => (
        <NavLink key={it.key} to={it.to} title={it.label}
          className={({ isActive }) => `relative flex flex-col items-center gap-0.5 rounded px-1 py-1.5 text-[10px] max-md:flex-1 ${isActive ? 'bg-panel2 text-strong' : 'text-muted hover:bg-hover hover:text-text'}`}>
          <svg viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[it.key]}</svg>
          <span>{it.label}</span>
          {it.key === 'news' && soon > 0 && (
            <b data-testid="news-badge" aria-label={`${soon} high-impact events within 24 hours`}
              className="absolute right-1 top-0.5 min-w-[15px] rounded-full bg-down px-1 text-center text-[9px] leading-[15px] text-white">{soon}</b>
          )}
        </NavLink>
      ))}
      <a href="/old" title="Old screen"
        className="mt-auto rounded px-1 py-1 text-center text-[9px] text-muted hover:bg-hover hover:text-text max-md:mt-0 max-md:hidden">Old screen</a>
    </nav>
  )
}
