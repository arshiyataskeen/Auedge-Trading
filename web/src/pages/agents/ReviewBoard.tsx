import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  qk, useApplyReview, useBacktestStatus, useReview, useRefreshAnalysis, useReviewAuto, useReviewVote, useRunReview, useUndoReview,
} from '../../api/endpoints'
import type { Review } from '../../api/types'
import QueryCard from '../../components/QueryCard'
import { money, toneOf } from '../../lib/format'
import { Alert, btnCls, btnPrimaryCls, Card, Meta, Sect } from '../journal/ui'
import { labelOf, when } from './logic'

const TONE = { up: 'text-up', dn: 'text-down', '': '' } as const
const Usd = ({ v }: { v: number }) => <span className={`tabular-nums ${TONE[toneOf(v)]}`.trim()}>{money(v)}</span>

const REVIEW_POLL_MS = 5 * 60_000

/** Old rvLoad/rvRender: the weekly Review board (vote chips, last review, change log, run / undo / auto). */
export default function ReviewBoard() {
  const qc = useQueryClient()
  const review = useReview()
  const [polling, setPolling] = useState(false)
  const status = useBacktestStatus(polling)
  const st = status.data
  const running = !!st?.running && String(st.id).startsWith('rv_')
  const busy = !!st?.running && !running
  useEffect(() => { setPolling(running) }, [running])

  // Every 5 min re-read the review list and the status (a scheduled review may have started); old rvLoad.
  useEffect(() => {
    const t = setInterval(() => {
      qc.invalidateQueries({ queryKey: qk.review }); qc.invalidateQueries({ queryKey: qk.btStatus })
    }, REVIEW_POLL_MS)
    return () => clearInterval(t)
  }, [qc])
  // New votes change live weights: re-run the analysis (old loadAgents(true) = GET /api/analysis?refresh=true).
  const refresh = useRefreshAnalysis()
  const refreshRef = useRef(refresh.mutate)
  refreshRef.current = refresh.mutate
  const was = useRef(false)
  useEffect(() => {
    if (was.current && !running) { qc.invalidateQueries({ queryKey: qk.review }); refreshRef.current() }
    was.current = running
  }, [running, qc])

  const vote = useReviewVote(), run = useRunReview(), undo = useUndoReview(), auto = useReviewAuto(), apply = useApplyReview()
  const [err, setErr] = useState('')
  const act = async (fn: () => Promise<unknown>) => {
    setErr('')
    try { await fn() } catch (e) { setErr((e as Error).message) }
  }
  const anyPending = vote.isPending || run.isPending || undo.isPending || auto.isPending || apply.isPending || refresh.isPending

  const actThenRefresh = async (fn: () => Promise<unknown>) => {
    setErr('')
    try { await fn() } catch (e) { setErr((e as Error).message); return }
    try { await refresh.mutateAsync() } catch (e) { setErr(`Saved, but refreshing the analysis failed: ${(e as Error).message}`) }
  }

  const onVote = (name: string, turnOn: boolean) => {
    if (!window.confirm(`${turnOn ? 'Switch ON' : 'Switch OFF'} the ${labelOf(name)} vote? It is logged and can be undone.`)) return
    void actThenRefresh(() => vote.mutateAsync({ agent: name, on: turnOn }))
  }
  const onUndo = () => {
    if (!window.confirm('Undo the last vote change?')) return
    void actThenRefresh(() => undo.mutateAsync())
  }
  const onRun = () => void act(async () => { await run.mutateAsync(false); await qc.invalidateQueries({ queryKey: qk.btStatus }) })

  return (
    <QueryCard query={review} title="Review board">
      {(d) => <Board d={d} err={err} anyPending={anyPending} running={running} busy={busy} st={st}
        onVote={onVote} onUndo={onUndo} onRun={onRun}
        onApply={(id) => void actThenRefresh(() => apply.mutateAsync(id))}
        onAuto={(on) => void act(() => auto.mutateAsync(on))} />}
    </QueryCard>
  )
}

function Board({ d, err, anyPending, running, busy, st, onVote, onUndo, onRun, onApply, onAuto }: {
  d: Review; err: string; anyPending: boolean; running: boolean; busy: boolean; st: ReturnType<typeof useBacktestStatus>['data']
  onVote: (name: string, on: boolean) => void; onUndo: () => void; onRun: () => void; onApply: (id: string) => void; onAuto: (on: boolean) => void
}) {
  const off = new Set(d.votes.off)
  const L = d.last
  const pr = st?.progress
  const pct = pr?.total ? Math.min(100, Math.round((100 * pr.done) / pr.total)) : 0
  const same = (a: string[], b: string[]) => JSON.stringify([...a].sort()) === JSON.stringify([...b].sort())
  const pending = !!L && !L.apply && !L.applied && (L.changes || []).length > 0 && same(L.votes_before, [...off]) && !d.log.some((e) => e.review === L.id)

  return (
    <Card label="Review board">
      <Sect>Review board · keeps the team honest</Sect>
      <Meta cls="mb-2">
        Every week it re-tests each agent's vote on 6 months and on the last month. A vote is switched <b>off</b> only if results are better
        without it in <b>both halves</b> of the 6 months and the last month is not worse (and back <b>on</b> by the same rule). At most 2 changes a
        week, at least {L ? L.rules.min_voters : 5} agents keep voting, and the safety rules (discipline, daily limits, news) are never touched.
        Switched-off agents still show their view and levels.
      </Meta>
      {err && <div className="mb-2"><Alert>{err}</Alert></div>}
      <div role="group" aria-label="Agent votes" className="flex flex-wrap gap-1.5">
        {d.agents.map((a) => {
          const isOff = off.has(a.name)
          return (
            <button key={a.name} type="button" aria-pressed={!isOff} disabled={anyPending} onClick={() => onVote(a.name, isOff)}
              title={isOff ? 'Vote is OFF. Click to switch it back on.' : 'Vote is ON. Click to switch it off.'}
              className={`rounded-[14px] border px-2.5 py-1 text-[12.5px] disabled:opacity-60 ${isOff
                ? 'border-line2 text-muted line-through' : 'border-transparent bg-up-bg text-up'}`}>
              {isOff ? '○' : '●'} {labelOf(a.name)}
            </button>
          )
        })}
      </div>
      <Meta cls="mb-2.5 mt-1">● votes · ○ switched off · click to change by hand (logged, can be undone)</Meta>

      {running ? (
        <div className="mt-2.5">
          <div role="progressbar" aria-label="Review progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
            className="mb-1 h-1.5 overflow-hidden rounded bg-panel2"><span className="block h-full bg-accent transition-[width]" style={{ width: `${pct}%` }} /></div>
          <Meta>Review running · {pr?.phase || 'starting'} · {pct}%</Meta>
        </div>
      ) : L ? (
        <div className="border-t border-line pt-2">
          <b>Last review</b> <span className="text-[11.5px] text-muted">{when(L.made_at)}{L.apply ? '' : ' · suggest only'}</span>
          <div className="mt-1 text-[12.5px]">{L.summary}</div>
          {(L.candidates || []).length > 0 && (
            <ul className="mt-1.5 list-disc pl-5 text-[12.5px] leading-[1.5]">
              {L.candidates.map((c, i) => (
                <li key={i}>
                  {labelOf(c.agent)} vote <b>{c.action.toUpperCase()}</b>: 6 months <Usd v={c.gain_6m} /> (halves <span className="tabular-nums">{money(c.halves_6m[0])}</span> / <span className="tabular-nums">{money(c.halves_6m[1])}</span>),
                  {' '}last month <Usd v={c.gain_month} />
                  {c.skipped ? <> · <span className="text-[11.5px] text-muted">skipped: {c.skipped}</span></> : null}
                </li>
              ))}
            </ul>
          )}
          {L.confirm?.result && <Meta>{L.confirm.result}</Meta>}
          {pending && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button type="button" className={btnPrimaryCls} disabled={anyPending} onClick={() => onApply(L.id)}>Apply these changes</button>
              <Meta>Suggest-only review: nothing changed yet.</Meta>
            </div>
          )}
        </div>
      ) : <Meta>No review yet. The first one runs automatically this weekend.</Meta>}

      {d.log.length > 0 && (
        <>
          <h3 className="mb-1 mt-2.5 text-[11px] font-semibold uppercase tracking-[.06em] text-muted">Changes</h3>
          <ul className="list-disc pl-5 text-[12.5px] leading-[1.5]">
            {d.log.slice(0, 6).map((e, i) => (
              <li key={i}>
                <span className="text-[11.5px] text-muted">{when(e.t)} · {e.by}</span> ·{' '}
                {(e.changes || []).map((c) => `${labelOf(c.agent)} ${c.action === 'off' ? 'off' : 'on'}`).join(', ') || 'no change'}
                {e.note && e.by !== 'you' ? <> <span className="text-[11.5px] text-muted">({e.note})</span></> : null}
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="my-2 flex flex-wrap items-center gap-2">
        <button type="button" className={btnCls} disabled={!!st?.running || anyPending} onClick={onRun}>Run review now (about 10 min, low priority)</button>
        {d.log.length > 0 && (
          <button type="button" className={btnCls} disabled={anyPending} title="Put back the votes from before the last change" onClick={onUndo}>Undo last change</button>
        )}
        <label title="Off = the board only suggests; you apply with one click" className="flex items-center gap-1.5 text-[12.5px]">
          <input type="checkbox" checked={d.votes.auto_apply} disabled={anyPending} onChange={(e) => onAuto(e.target.checked)} /> Apply changes automatically
        </label>
      </div>
      <Meta>Next automatic review: {when(d.next_due)} or the first weekend after. {busy ? 'A backtest is running now.' : ''}</Meta>
    </Card>
  )
}
