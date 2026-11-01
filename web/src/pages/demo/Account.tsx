import { useMemo, useState } from 'react'
import { useDemo } from '../../api/endpoints'
import { useLivePrice } from '../../api/live'
import EmptyState from '../../components/EmptyState'
import EquityChart from '../../components/EquityChart'
import MoneyText from '../../components/MoneyText'
import QueryCard from '../../components/QueryCard'
import StatGrid from '../../components/StatGrid'
import TradeReplay from '../../components/TradeReplay'
import { money, price } from '../../lib/format'
import { card, sect } from '../backtest/ui'
import { demoToTrade, hm, withLivePrice } from './logic'

const when = (ts: number) =>
  new Date(ts * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

type Picked = { kind: 'open' | 'closed'; id: number }

/** Port of the old Demo account tab (renderDemoLive + liveDemoTick). */
export default function Account() {
  const q = useDemo()
  const live = useLivePrice()
  const [pick, setPick] = useState<Picked | null>(null)

  const d = q.data
  // liveDemoTick: open P&L and equity follow the top-bar price between the 30 s refetches.
  const view = useMemo(
    () => (d ? withLivePrice(d.open, d.balance, d.equity, live.price) : null),
    [d, live.price],
  )

  return (
    <QueryCard query={q} title="Demo account">
      {(demo) => {
        const open = view!.open, equity = view!.equity
        const nowPrice = open.length && live.price != null ? live.price : demo.price
        const since = equity - demo.start
        const picked = pick ? (pick.kind === 'open' ? open : demo.closed).find((x) => x.id === pick.id) : undefined
        const trade = picked ? demoToTrade(picked) : null
        return (
          <div className="grid grid-cols-1 gap-3 min-[900px]:grid-cols-[minmax(0,1fr)_minmax(340px,28%)]">
            <div className="flex min-w-0 flex-col gap-3">
              {open.length ? open.map((t) => (
                <section key={t.id} className={card} aria-label="Open demo position">
                  <h2 className={sect}>Open demo position · {t.lot} lot</h2>
                  <button type="button" onClick={() => setPick({ kind: 'open', id: t.id })} title="Click to see it on a chart"
                    aria-label={`Open ${t.side} position, see it on a chart`} className="block w-full text-left">
                    <div className="mb-2 flex items-baseline gap-3">
                      <b className={t.side === 'BUY' ? 'text-up' : 'text-down'}>{t.side}</b>
                      <b className="text-[16px] tabular-nums text-strong">{price(t.entry)}</b>
                      <span className="flex-1" />
                      <b data-testid="open-pnl" className="text-[20px]"><MoneyText v={t.unrealised} /></b>
                    </div>
                    <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                      <Level k="Price now" v={price(nowPrice)} sub="live" />
                      <Level k="Stop" v={price(t.stop_now)} sub={t.half ? 'moved to entry (risk free)' : 'original stop'} cls="text-down" />
                      <Level k="Half off · 1R" v={price(t.be)} sub={t.half ? 'done: half closed' : 'not reached yet'} cls="text-up" />
                      <Level k="Target" v={price(t.t1)} sub="rest closes here" cls="text-up" />
                      <Level k="Opened" v={hm(t.ts)} sub={new Date(t.ts * 1000).toLocaleDateString()} />
                      <Level k="Expires" v={hm(t.ts + 86400)} sub="closes after 24 h" />
                    </div>
                  </button>
                </section>
              )) : <EmptyState>No open demo position. One opens automatically on the next BUY NOW / SELL NOW.</EmptyState>}

              {demo.curve.length > 0 && (
                <section className={card} aria-label="Demo equity">
                  <h2 className={sect}>Demo equity · profit / loss since start</h2>
                  <EquityChart curve={demo.curve} unit="$" />
                </section>
              )}

              <section className={card} aria-label="Closed demo trades">
                <h2 className={sect}>Closed demo trades · newest first · click to replay</h2>
                {demo.closed.length ? demo.closed.map((t) => (
                  <button key={t.id} type="button" onClick={() => setPick({ kind: 'closed', id: t.id })} title="Click to replay"
                    aria-label={`Replay ${when(t.ts)} ${t.side} ${price(t.entry)} to ${price(t.exit_price)}`}
                    className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 border-b border-line py-1.5 text-left text-[12.5px] last:border-0 hover:bg-hover sm:grid-cols-[auto_auto_minmax(0,1fr)_auto]">
                    <span className="tabular-nums text-muted">{when(t.ts)}</span>
                    <span className={`hidden font-bold sm:inline ${t.side === 'BUY' ? 'text-up' : 'text-down'}`}>{t.side}</span>
                    <span className="hidden min-w-0 truncate sm:block">
                      <span className="tabular-nums">{price(t.entry)} → {price(t.exit_price)}</span> <span className="text-muted">{t.why || t.status}</span>
                    </span>
                    <b className="text-right"><MoneyText v={t.usd} /></b>
                  </button>
                )) : (
                  <p className="text-[12px] text-muted">None yet. The first one appears after AuEdge&apos;s first BUY NOW / SELL NOW while the market is open.
                    Meanwhile, see how it would have traded in the Backtest page.</p>
                )}
              </section>
            </div>

            <aside className="flex min-w-0 flex-col gap-3">
              <section className={card} aria-label="Balance">
                <h2 className={sect}>Demo account · automatic · no real money</h2>
                <div className="text-[11px] text-muted">Balance (equity incl. open trade)</div>
                <div data-testid="demo-equity" className={`text-[28px] font-bold tabular-nums ${since > 0 ? 'text-up' : since < 0 ? 'text-down' : 'text-strong'}`}>
                  ${Math.round(equity).toLocaleString('en-US')}
                </div>
                <div className="mb-3 text-[12px] text-muted">
                  <MoneyText v={since} /> since start (${demo.start.toLocaleString('en-US')}) · {demo.lot} lot per trade
                </div>
                <StatGrid stats={[
                  { label: 'Today', value: <MoneyText v={demo.today} /> },
                  { label: 'This week', value: <MoneyText v={demo.week} /> },
                  { label: 'Closed trades', value: demo.trades },
                  { label: 'Won', value: demo.win_rate != null ? `${demo.win_rate}%` : '—' },
                ]} />
                <p className="mt-3 text-[11.5px] text-muted">
                  AuEdge opens a demo position by itself on every BUY NOW / SELL NOW that passes the Discipline rules (2 trades a day, news, Friday,
                  {' '}{money(-350)} / {money(150)} per day), then manages it like the plan: stop, half off at 1R with the stop moved to the entry,
                  target, 24-hour expiry. $0.30 cost per side. It never touches a real broker. Positions are checked every 15 minutes on real candle highs and lows.
                </p>
              </section>
            </aside>

            {trade && <TradeReplay trade={trade} lot={trade.lot} onClose={() => setPick(null)} />}
          </div>
        )
      }}
    </QueryCard>
  )
}

function Level({ k, v, sub, cls = '' }: { k: string; v: string; sub: string; cls?: string }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-app px-[9px] py-[7px]">
      <span className="block text-[11px] text-muted">{k}</span>
      <b className={`block text-[15px] tabular-nums ${cls}`}>{v}</b>
      <i className="block truncate text-[11px] not-italic text-muted">{sub}</i>
    </div>
  )
}
