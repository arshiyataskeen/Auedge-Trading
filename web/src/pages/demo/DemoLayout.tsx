import { useNavigate } from 'react-router-dom'
import PageHeader from '../../components/PageHeader'
import Tabs from '../../components/Tabs'
import Account from './Account'
import CalendarPanel from './CalendarPanel'

const ITEMS = [{ key: 'account', label: 'Account' }, { key: 'calendar', label: 'Calendar' }]

/** Demo page shell: Account | Calendar tabs, each its own route (/demo, /demo/calendar). */
export default function DemoLayout({ tab }: { tab: 'account' | 'calendar' }) {
  const nav = useNavigate()
  return (
    <div>
      <PageHeader title="Demo" subtitle="AuEdge's own demo account: automatic, no broker, no real money." />
      <Tabs label="Demo" items={ITEMS} value={tab} onChange={(k) => nav(k === 'calendar' ? '/demo/calendar' : '/demo')}>
        <div className="pt-3"><Account /></div>
        <div className="pt-3"><CalendarPanel /></div>
      </Tabs>
    </div>
  )
}
