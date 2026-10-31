import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'

/** Fixed-height shell: the only scroll area is <main id="page">. */
export default function AppShell() {
  return (
    <div className="flex h-full bg-app text-text max-md:flex-col-reverse">
      <Sidebar />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <TopBar />
        <main id="page" className="min-h-0 flex-1 overflow-y-auto p-3 max-md:pb-16">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
