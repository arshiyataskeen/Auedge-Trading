import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useCreateTrade, useDeleteTrade, useUpdateTrade } from '../../api/endpoints'
import type { JournalAccount, JournalTrade, TradeBody } from '../../api/types'
import Modal from '../../components/Modal'
import { money } from '../../lib/format'
import {
  EMOTIONS, initialTrade, jDate, readImage, riskNumbers, SETUPS, tradeBody, type TradeFormState, type TradeValues,
} from './logic'
import { btnCls, btnPrimaryCls, inputCls, linkBtn, Meta } from './ui'

const L = ({ t, children, title }: { t: string; children: ReactNode; title?: string }) =>
  <label title={title} className="flex flex-col gap-0.5 text-[11px] text-muted"><span>{t}</span>{children}</label>
const seg = (on: boolean) => `rounded border px-2.5 py-1 text-[12px] ${on ? 'border-accent bg-acc-bg text-strong' : 'border-line bg-panel text-muted hover:bg-hover'}`

type Props = {
  /** the trade being edited (none = add) */
  trade?: JournalTrade
  /** starting values for a new trade (addCall) */
  prefill?: Partial<TradeValues>
  /** accounts with their phases; undefined while loading */
  accounts: JournalAccount[] | undefined
  /** account preselected for a new trade */
  accountId?: number
  /** setups already used, offered next to the standard ones */
  knownSetups?: string[]
  onClose: () => void
  onSaved?: (body: TradeBody) => void
}

/** Port of tradeForm / riskHint / readImg / the paste handler / savetrade / deltrade. */
export default function TradeForm({ trade: t, prefill, accounts, accountId, knownSetups = [], onClose, onSaved }: Props) {
  const v = useMemo<TradeValues>(() => ({ side: 'BUY', symbol: 'XAUUSD', opened_at: Math.round(Date.now() / 1000), ...prefill, ...t }), [prefill, t])
  const pool = useMemo(() => (accounts ?? []).filter((a) => t || (!a.archived && a.current && !a.current.result)), [accounts, t])
  const accId = t ? t.account_id : (accountId != null && pool.some((a) => a.id === accountId) ? accountId : pool[0]?.id)
  const defPhase = (a: JournalAccount | undefined) => (t && a?.id === t.account_id ? t.phase_id : a?.phases.find((p) => !p.result)?.id)
  const [f, setF] = useState<TradeFormState>(() => initialTrade(v, accId, defPhase(pool.find((a) => a.id === accId))))
  const [err, setErr] = useState('')
  const create = useCreateTrade(), update = useUpdateTrade(), del = useDeleteTrade()
  const busy = create.isPending || update.isPending || del.isPending
  const set = <K extends keyof TradeFormState>(k: K, val: TradeFormState[K]) => setF((s) => ({ ...s, [k]: val }))

  // accounts may arrive after the form opened (dashboard link): adopt the default account then
  useEffect(() => {
    if (!f.acc && accId != null) setF((s) => ({ ...s, acc: String(accId), phase: String(defPhase(pool.find((a) => a.id === accId)) ?? '') }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accId])

  const acc = pool.find((a) => a.id === +f.acc)
  const risk = riskNumbers(acc, f)

  const pickImage = async (file: File | undefined) => {
    if (!file) return
    try { set('image', await readImage(file)); setErr('') } catch (e) { setErr((e as Error).message) }
  }
  useEffect(() => {
    function onPaste(e: ClipboardEvent) {
      const item = [...(e.clipboardData?.items ?? [])].find((i) => i.type.startsWith('image/'))
      const file = item?.getAsFile()
      if (file) { e.preventDefault(); void pickImage(file) }
    }
    document.addEventListener('paste', onPaste)
    return () => document.removeEventListener('paste', onPaste)
  })

  async function save() {
    setErr('')
    const body = tradeBody(f, { source: v.source, auedge: v.auedge })
    if (!body.opened_at) { setErr('Set the open time.'); return }
    try {
      if (t) await update.mutateAsync({ id: t.id, body }); else await create.mutateAsync(body)
      onSaved?.(body)
      onClose()
    } catch (e) { setErr((e as Error).message) }
  }
  async function remove() {
    if (!t || !window.confirm('Delete this trade from the journal? This cannot be undone.')) return
    try { await del.mutateAsync(t.id); onSaved?.({ account_id: t.account_id }); onClose() } catch (e) { setErr((e as Error).message) }
  }

  const title = t ? 'Trade' : v.source === 'auedge' ? 'Add AuEdge call to journal' : 'Add trade'
  if (accounts === undefined || !pool.length) {
    return (
      <Modal label={title} onClose={onClose} width={420}>
        <h2 className="pr-9 text-[16px] font-bold text-strong">{title}</h2>
        <p className="mt-2 text-[12.5px] text-muted">{accounts === undefined ? 'Loading accounts…' : 'Create an account first (Dashboard → New account).'}</p>
      </Modal>
    )
  }
  const known = [...new Set([...SETUPS, ...knownSetups])]
  const inp = (k: keyof TradeFormState, label: string, o: { step?: string; w?: number; type?: string; title?: string; ph?: string } = {}) => (
    <L t={label} title={o.title}>
      <input type={o.type ?? 'number'} step={o.type ? undefined : (o.step ?? '0.01')} style={o.w ? { width: o.w } : undefined} className={inputCls}
        value={f[k] as string} placeholder={o.ph} onChange={(e) => set(k, e.target.value as never)} />
    </L>
  )
  const savedImg = t?.image && f.image == null
  const hints: ReactNode[] = []
  if (risk) {
    if (risk.risk != null) hints.push(<>Risk if the stop is hit: <b>${risk.risk.toFixed(0)}</b> ({risk.riskPct!.toFixed(2)}% of the account)</>)
    if (risk.room != null) {
      hints.push(risk.over ? <span className="text-down">more than today's loss room ({money(risk.room, { sign: false })})!</span>
        : <>today's loss room left: {money(risk.room, { sign: false })}</>)
    }
    if (risk.lots05 != null) hints.push(<>Lots for 0.5% risk: <b>{risk.lots05.toFixed(2)}</b> · for 1%: <b>{risk.lots1!.toFixed(2)}</b></>)
    if (risk.pnl != null) hints.push(<>P&amp;L from prices: <b>{money(risk.pnl)}</b> (type your broker's number if different)</>)
  }
  return (
    <Modal label={title} onClose={onClose}>
      <h2 className="mb-3 pr-9 text-[16px] font-bold text-strong">{title}</h2>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <L t="Account">
            <select className={inputCls} value={f.acc} onChange={(e) => {
              const a = pool.find((x) => x.id === +e.target.value)
              setF((s) => ({ ...s, acc: e.target.value, phase: String(a?.phases.find((p) => !p.result)?.id ?? '') }))
            }}>
              {pool.map((a) => <option key={a.id} value={a.id}>{a.name}{a.archived ? ' (archived)' : ''}</option>)}
            </select>
          </L>
          <L t="Phase">
            <select className={inputCls} value={f.phase} onChange={(e) => set('phase', e.target.value)}>
              {(acc?.phases ?? []).map((p) => <option key={p.id} value={p.id}>{p.is_funded ? 'Funded' : p.name}{p.result ? ` (${p.result})` : ''}</option>)}
            </select>
          </L>
          {inp('symbol', 'Symbol', { type: 'text', w: 90 })}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex gap-1" role="group" aria-label="Side">
            {(['BUY', 'SELL'] as const).map((s) => <button key={s} type="button" aria-pressed={f.side === s} className={seg(f.side === s)} onClick={() => set('side', s)}>{s}</button>)}
          </div>
          {inp('opened', 'Opened', { type: 'datetime-local' })}
          {inp('closed', 'Closed', { type: 'datetime-local' })}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          {inp('lots', 'Lots', { w: 80 })}{inp('entry', 'Entry', { w: 100 })}{inp('stop', 'Stop', { w: 100 })}{inp('target', 'Target', { w: 100 })}{inp('exit', 'Exit', { w: 100 })}
        </div>
        <Meta cls="min-h-[1.2em]">{hints.map((x, i) => <span key={i}>{i ? ' · ' : ''}{x}</span>)}</Meta>
        <div className="flex flex-wrap items-end gap-3">
          {inp('pnl', 'P&L $', { title: "Your broker's real profit/loss. Leave empty to work it out from entry, exit and lots.", ph: 'auto', w: 100 })}
          {inp('com', 'Commission $', { w: 100 })}
          <L t="Setup">
            <input list="jtSetups" className={`${inputCls} w-[170px]`} value={f.setup} onChange={(e) => set('setup', e.target.value)} />
            <datalist id="jtSetups">{known.map((x) => <option key={x} value={x} />)}</datalist>
          </L>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[12px]">
          <span>Followed my plan?</span>
          <div className="flex gap-1" role="group" aria-label="Followed my plan">
            {([['Yes', 1], ['No', 0]] as const).map(([l, n]) => (
              <button key={l} type="button" aria-pressed={f.plan === n} className={seg(f.plan === n)} onClick={() => set('plan', f.plan === n ? null : n)}>{l}</button>
            ))}
          </div>
          <span>Rating</span>
          <div className="flex" role="group" aria-label="Rating">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} type="button" aria-label={`${n} stars`} aria-pressed={f.rate === n} onClick={() => set('rate', n)}
                className={`text-[18px] ${f.rate >= n ? 'text-warn' : 'text-muted'}`}>★</button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Mood">
          <span className="mr-1 text-[12px]">Mood</span>
          {EMOTIONS.map((e) => <button key={e} type="button" aria-pressed={f.mood === e} className={seg(f.mood === e)} onClick={() => set('mood', f.mood === e ? null : e)}>{e}</button>)}
        </div>
        <label className="block text-[11.5px] text-muted">Mistakes / lessons
          <textarea rows={2} className={`${inputCls} mt-0.5 block w-full`} value={f.mist} onChange={(e) => set('mist', e.target.value)} /></label>
        <label className="block text-[11.5px] text-muted">Notes
          <textarea rows={3} className={`${inputCls} mt-0.5 block w-full`} value={f.notes} onChange={(e) => set('notes', e.target.value)} /></label>
        <div className="flex flex-wrap items-center gap-3">
          <L t="Screenshot">
            <input type="file" accept="image/png,image/jpeg,image/webp" className="text-[12px]" onChange={(e) => void pickImage(e.target.files?.[0])} />
          </L>
          <Meta>or paste an image (Ctrl+V) while this form is open</Meta>
        </div>
        <div>
          {f.image === 'remove' ? <Meta>Screenshot will be removed when you save.</Meta>
            : f.image ? <img src={f.image} alt="Trade screenshot" className="max-h-[220px] max-w-full rounded border border-line" />
            : savedImg ? (
              <div className="flex flex-col items-start gap-1">
                <img src={`/api/journal/file/${t!.image}`} alt="Trade screenshot" className="max-h-[220px] max-w-full rounded border border-line" />
                <button type="button" className={linkBtn} onClick={() => set('image', 'remove')}>Remove screenshot</button>
              </div>
            ) : null}
        </div>
        {v.auedge && (
          <Meta>From AuEdge: {String(v.auedge.action ?? '')} · confidence {String(v.auedge.confidence ?? '—')}% · {jDate(v.auedge.t as number)}</Meta>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={btnPrimaryCls} disabled={busy} onClick={save}>{t ? 'Save' : 'Add to journal'}</button>
          {t && <button type="button" className={`${btnCls} text-down`} disabled={busy} onClick={remove}>Delete trade</button>}
          {err && <span role="alert" className="text-[12px] text-warn">{err}</span>}
        </div>
      </div>
    </Modal>
  )
}
