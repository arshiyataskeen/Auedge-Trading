import { useState, type ReactNode } from 'react'
import { useCreateAccount, useUpdateAccount } from '../../api/endpoints'
import type { JournalAccount } from '../../api/types'
import Modal from '../../components/Modal'
import {
  accountBody, addPhase, applyPreset, blankRules, MAX_PHASES, PRESETS, removePhase, rulesFromAccount,
  type FundedRow, type PhaseRow, type PresetKey, type RulesForm,
} from './logic'
import { btnCls, btnPrimaryCls, inputCls, linkBtn, Meta, Sect } from './ui'

const L = ({ t, children, title }: { t: string; children: ReactNode; title?: string }) =>
  <label title={title} className="flex flex-col gap-0.5 text-[11px] text-muted"><span>{t}</span>{children}</label>
const TypeSel = ({ v, on, label }: { v: string; on: (v: string) => void; label: string }) => (
  <L t={label}>
    <select className={inputCls} value={v} onChange={(e) => on(e.target.value)}>
      <option value="static">static</option><option value="trailing">trailing</option>
    </select>
  </L>
)

/** Port of accountForm / phaseRow: new or edit (size is fixed once created). */
export default function AccountForm({ account, onClose, onSaved }: { account?: JournalAccount; onClose: () => void; onSaved: (id: number) => void }) {
  const [name, setName] = useState(account?.name ?? '')
  const [firm, setFirm] = useState(account?.firm ?? '')
  const [size, setSize] = useState(account ? String(account.size) : '')
  const [notes, setNotes] = useState(account?.notes ?? '')
  const [rules, setRules] = useState<RulesForm>(() => (account ? rulesFromAccount(account) : blankRules()))
  const [err, setErr] = useState('')
  const create = useCreateAccount(), update = useUpdateAccount()
  const busy = create.isPending || update.isPending

  const setPhase = (i: number, k: keyof PhaseRow, v: string) =>
    setRules((r) => ({ ...r, phases: r.phases.map((p, j) => (j === i ? { ...p, [k]: v } : p)) }))
  const setFunded = (k: keyof FundedRow, v: string) => setRules((r) => ({ ...r, funded: { ...r.funded, [k]: v } }))

  async function save() {
    setErr('')
    const body = accountBody({ name, firm, size, notes }, rules)
    try {
      if (account) { await update.mutateAsync({ id: account.id, body }); onSaved(account.id) }
      else { const r = await create.mutateAsync(body); onSaved(r.id ?? 0) }
      onClose()
    } catch (e) { setErr((e as Error).message) }
  }

  const num = (v: string, on: (v: string) => void, step = '0.1', ph?: string) =>
    <input type="number" step={step} className={`${inputCls} w-[84px]`} value={v} placeholder={ph} onChange={(e) => on(e.target.value)} />
  return (
    <Modal label={account ? 'Edit account' : 'New prop-firm account'} onClose={onClose}>
      <h2 className="mb-3 pr-9 text-[16px] font-bold text-strong">{account ? 'Edit account' : 'New prop-firm account'}</h2>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <L t="Name"><input className={`${inputCls} w-[200px]`} value={name} placeholder="e.g. 10K Challenge #1" onChange={(e) => setName(e.target.value)} /></L>
          <L t="Firm"><input className={`${inputCls} w-[160px]`} value={firm} placeholder="your prop firm" onChange={(e) => setFirm(e.target.value)} /></L>
          <L t="Account size $">
            <input type="number" step="1000" className={`${inputCls} w-[110px]`} value={size} disabled={!!account} placeholder="10000" onChange={(e) => setSize(e.target.value)} />
          </L>
        </div>
        <div>
          <Sect>Phases · your firm's rules (percent of the account size)</Sect>
          {!account && (
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Meta>Start from:</Meta>
              {(Object.keys(PRESETS) as PresetKey[]).map((k) => (
                <button key={k} type="button" className={btnCls} onClick={() => setRules((r) => applyPreset(r, k))}>{PRESETS[k].label}</button>
              ))}
            </div>
          )}
          <div className="flex flex-col gap-2">
            {rules.phases.map((p, i) => (
              <div key={i} role="group" aria-label={`Phase ${i + 1} rules`} className="flex flex-wrap items-end gap-2 rounded border border-line p-2">
                <input aria-label="Phase name" className={`${inputCls} w-[110px]`} value={p.name} onChange={(e) => setPhase(i, 'name', e.target.value)} />
                <L t="Target %">{num(p.target_pct, (v) => setPhase(i, 'target_pct', v))}</L>
                <L t="Daily loss %">{num(p.daily_loss_pct, (v) => setPhase(i, 'daily_loss_pct', v))}</L>
                <L t="Max loss %">{num(p.max_loss_pct, (v) => setPhase(i, 'max_loss_pct', v))}</L>
                <TypeSel label="Max loss type" v={p.max_loss_type} on={(v) => setPhase(i, 'max_loss_type', v)} />
                <L t="Min days">{num(p.min_days, (v) => setPhase(i, 'min_days', v), '1')}</L>
                <L t="Consistency %" title="Best single day may be at most this % of the total profit (leave empty if your firm has no such rule)">
                  {num(p.consistency_pct, (v) => setPhase(i, 'consistency_pct', v), '1', 'none')}
                </L>
                <button type="button" className={linkBtn} aria-label="Remove phase" onClick={() => setRules((r) => ({ ...r, phases: removePhase(r.phases, i) }))}>✕</button>
              </div>
            ))}
          </div>
          <button type="button" className={`${linkBtn} mt-1`} disabled={rules.phases.length >= MAX_PHASES}
            onClick={() => setRules((r) => ({ ...r, phases: addPhase(r.phases) }))}>＋ Add a phase</button>
        </div>
        <div>
          <Sect>Funded account rules</Sect>
          <div role="group" aria-label="Funded rules" className="flex flex-wrap items-end gap-2 rounded border border-line p-2">
            <b className="min-w-[70px] text-strong">Funded</b>
            <L t="Funded daily loss %">{num(rules.funded.daily_loss_pct, (v) => setFunded('daily_loss_pct', v))}</L>
            <L t="Funded max loss %">{num(rules.funded.max_loss_pct, (v) => setFunded('max_loss_pct', v))}</L>
            <TypeSel label="Funded max loss type" v={rules.funded.max_loss_type} on={(v) => setFunded('max_loss_type', v)} />
            <L t="Profit split %">{num(rules.funded.profit_split, (v) => setFunded('profit_split', v), '1')}</L>
            <L t="Funded consistency %" title="Best single day may be at most this % of the profit (for payouts)">
              {num(rules.funded.consistency_pct, (v) => setFunded('consistency_pct', v), '1', 'none')}
            </L>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <L t="New day starts at">
            <select className={inputCls} value={rules.reset} onChange={(e) => setRules((r) => ({ ...r, reset: e.target.value }))}>
              <option value="utc">00:00 UTC</option><option value="prague">00:00 Prague (CE/CEST, FTMO-style)</option>
              <option value="newyork">17:00 New York</option><option value="india">00:00 India</option>
            </select>
          </L>
          <L t="Daily loss counted from">
            <select className={inputCls} value={rules.daily_base} onChange={(e) => setRules((r) => ({ ...r, daily_base: e.target.value }))}>
              <option value="initial">the account size</option><option value="day_start">that day's starting balance</option>
            </select>
          </L>
        </div>
        <Meta>Static max loss = fixed level below the phase's starting balance. Trailing = follows your highest balance. Consistency % = your best single day may be
          at most this share of the total profit (e.g. 40); leave empty if your firm has no such rule.</Meta>
        <label className="block text-[11.5px] text-muted">Notes (payout dates, login, anything)
          <textarea rows={3} className={`${inputCls} mt-0.5 block w-full`} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={btnPrimaryCls} disabled={busy} onClick={save}>{account ? 'Save changes' : 'Create account'}</button>
          {err && <span role="alert" className="text-[12px] text-warn">{err}</span>}
        </div>
        {account && <Meta>Changing the rules re-checks every past trade with the new rules.</Meta>}
      </div>
    </Modal>
  )
}
