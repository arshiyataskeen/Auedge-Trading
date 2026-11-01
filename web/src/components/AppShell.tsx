import { Outlet } from 'react-router-dom'
import { useAnalysis } from '../api/endpoints'
import { NowAlertsContext, NowToast, useNowAlerts } from './NowAlerts'
import Sidebar from './Sidebar'
import TopBar from './TopBar'

/** Fixed-height shell: the only scroll area is <main id="page">. Owns the BUY/SELL NOW alerts so they fire on every page. */
export default function AppShell() {
  const alerts = useNowAlerts(useAnalysis().data)
  return (
    <NowAlertsContext.Provider value={alerts}>
      <div className="flex h-full bg-app text-text max-md:flex-col-reverse">
        <Sidebar />
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <TopBar />
          <main id="page" className="min-h-0 flex-1 overflow-y-auto p-3 max-md:pb-16">
            <Outlet />
          </main>
        </div>
      </div>
      {alerts.toast && <NowToast toast={alerts.toast} onClose={alerts.dismiss} />}
    </NowAlertsContext.Provider>
  )
}
