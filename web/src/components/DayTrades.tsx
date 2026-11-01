import type { BtTrade } from '../api/types'
import { price } from '../lib/format'
import MoneyText from './MoneyText'

const hm = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

type Props = {
  trades: BtTrade[]
  idx: number[]
  onReplay: (i: number) => void
  /** Show dollars (default: when every trade in `trades` has a dollar result) or R. */
  usd?: boolean
}

/** Port of btTradeLine: the trades of one day; each row opens the replay. */
export default function DayTrades({ trades, idx, onReplay, usd }: Props) {
  const dollars = usd ?? trades.every((t) => t.usd != null)
  return (
    <div>
      {idx.map((i) => {
        const t = trades[i]
        return (
          <button key={i} type="button" data-ti={i} title="Click to replay" onClick={() => onReplay(i)}
            className="mb-1 ml-1 grid w-[calc(100%-4px)] grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 border-l-2 border-line2 py-[5px] pl-2.5 text-left text-[12px] hover:bg-hover sm:grid-cols-[auto_auto_minmax(0,1fr)_auto]">
            <span className={`font-bold ${t.side === 'BUY' ? 'text-up' : 'text-down'}`}>{t.side}</span>
            <span className="hidden tabular-nums sm:inline">{hm(t.entry_t)} → {hm(t.exit_t)}</span>
            <span className="min-w-0 truncate text-muted">{price(t.entry)} → {price(t.exit)} · {t.why}</span>
            <b><MoneyText v={dollars ? t.usd : t.r} r={!dollars} /></b>
          </button>
        )
      })}
    </div>
  )
}
