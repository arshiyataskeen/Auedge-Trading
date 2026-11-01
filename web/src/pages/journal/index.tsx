import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAnalysis, useJournalAccounts, useJournalTrades } from '../../api/endpoints'
import type { JournalTrade } from '../../api/types'
import { STATUS, Bias, usd } from '../dashboard/Cards'
import AccountForm from './AccountForm'
import type { TradeValues } from './logic'
import Records from './Records'
import TradeForm from './TradeForm'
import { Alert, Card, linkBtn, Sect } from './ui'

type Modal = { k: 'account' } | { k: 'trade'; trade?: JournalTrade; prefill?: Partial<TradeValues> } | null

/** /journal: the accounts list and All records. `?new=1` opens the new-account form; `?call=1` opens the trade form pre-filled from AuEdge's call (old addCall). */
export default function JournalPage() {
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const [modal, setModal] = useState<Modal>(null)
  const [notice, setNotice] = useState('')
  const [archived, setArchived] = useState(false)
  const accounts = useJournalAccounts(true)
  const trades = useJournalTrades()
  const analysis = useAnalysis()

  const wantNew = sp.get('new') === '1', wantCall = sp.get('call') === '1'
  useEffect(() => {
    if (wantNew) { setModal({ k: 'account' }); setSp((p) => { p.delete('new'); return p }, { replace: true }) }
  }, [wantNew, setSp])
  useEffect(() => {
    if (!wantCall) return
    const d = analysis.data
    if (!d && !analysis.isError) return // wait for the analysis
    const p = d?.chief.plan
    const clear = () => setSp((x) => { x.delete('call'); return x }, { replace: true })
    if (!d || !p || p.kind !== 'now') {
      setNotice('There is no BUY / SELL NOW call right now, so there is nothing to add. Use ＋ Add trade to log one by hand.')
      return clear()
    }
    setNotice('')
    setModal({ k: 'trade', prefill: {
      side: p.side ?? 'BUY', entry: Math.round((((p.entry_lo ?? 0) + (p.entry_hi ?? 0)) / 2) * 100) / 100, stop: p.stop ?? undefined, target: p.t1 ?? undefined,
      setup: 'AuEdge NOW call', source: 'auedge', opened_at: Math.round(Date.now() / 1000),
      auedge: { action: p.action, confidence: d.chief.confidence, t: Math.round(Date.parse(d.generated_at) / 1000), be_at: p.be_at },
    } })
    clear()
  }, [wantCall, analysis.data, analysis.isError, setSp])

  const known = useMemo(() => [...new Set((trades.data?.trades ?? []).map((t) => t.setup).filter(Boolean))], [trades.data])
  const list = (accounts.data?.accounts ?? []).filter((a) => a.current && (archived || !a.archived))

  return (
    <div className="flex flex-col gap-3">
      {notice && <Alert tone="warn">{notice}</Alert>}
      <Card label="Accounts">
        <div className="flex items-center justify-between">
          <Sect>Accounts</Sect>
          <button type="button" className={linkBtn} onClick={() => setArchived((v) => !v)}>{archived ? 'Hide archived accounts' : 'Show archived accounts'}</button>
        </div>
        <div className="flex flex-wrap gap-2">
          {list.map((a) => {
            const [kind, text] = STATUS[a.current!.check.status] ?? ['NA' as const, a.current!.check.status]
            return (
              <Link key={a.id} to={`/journal/${a.id}`} className={`flex items-center gap-2 rounded border border-line bg-panel2 px-2.5 py-1.5 text-[12px] text-strong no-underline hover:bg-hover ${a.archived ? 'opacity-60' : ''}`}>
                <b>{a.name}</b><span className="tabular-nums text-muted">{usd(a.current!.check.balance)}</span><Bias kind={kind}>{text}</Bias>
              </Link>
            )
          })}
          {!list.length && <span className="text-[12px] text-muted">No accounts yet.</span>}
        </div>
      </Card>
      <Records onAddTrade={() => setModal({ k: 'trade' })} onNewAccount={() => setModal({ k: 'account' })} onOpenTrade={(t) => setModal({ k: 'trade', trade: t })} />
      {modal?.k === 'account' && <AccountForm onClose={() => setModal(null)} onSaved={(id) => { if (id) nav(`/journal/${id}`) }} />}
      {modal?.k === 'trade' && (
        <TradeForm trade={modal.trade} prefill={modal.prefill} accounts={accounts.data?.accounts} knownSetups={known as string[]} onClose={() => setModal(null)} />
      )}
    </div>
  )
}
