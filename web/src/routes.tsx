import { Navigate, type RouteObject } from 'react-router-dom'
import AppShell from './components/AppShell'
import AgentsPage from './pages/agents'
import BacktestPage from './pages/backtest'
import DashboardPage from './pages/dashboard'
import DemoPage from './pages/demo'
import DemoCalendarPage from './pages/demo/Calendar'
import JournalPage from './pages/journal'
import JournalAccountPage from './pages/journal/Account'
import NewsPage from './pages/news'
import TradePage from './pages/trade'

export const routes: RouteObject[] = [{
  path: '/',
  element: <AppShell />,
  children: [
    { index: true, element: <Navigate to="/trade" replace /> },
    { path: 'dashboard', element: <DashboardPage /> },
    { path: 'trade', element: <TradePage /> },
    { path: 'backtest', element: <BacktestPage /> },
    { path: 'journal', element: <JournalPage /> },
    { path: 'journal/:accountId', element: <JournalAccountPage /> },
    { path: 'demo', element: <DemoPage /> },
    { path: 'demo/calendar', element: <DemoCalendarPage /> },
    { path: 'news', element: <NewsPage /> },
    { path: 'agents', element: <AgentsPage /> },
  ],
}]
