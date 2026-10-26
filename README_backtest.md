# Backtest: how would the dashboard's trade plans have done?

The backtest replays the last few weeks of gold prices, 15 minutes at a time. At each step it shows the
dashboard's agents and the Chief **only the candles that existed at that moment** (never the future), takes
the trade plan they produce, and checks what price did afterwards. It places no real trades.

## How to run it

1. Run `run.bat` at least once first, so the `.venv` folder exists.
2. Open a Command Prompt in this folder (in File Explorer, click the address bar, type `cmd`, press Enter).
3. Type this and press Enter:

   ```
   .venv\Scripts\python.exe backtest.py
   ```

4. Wait about a minute. A summary prints in the window.
5. Open `data\backtest_report.html` (double-click it) for the full report with tables.

Optional extras (add them after `backtest.py`):

| Option | What it does |
| --- | --- |
| `--spread 0.50` | Assume a different cost per side in dollars (default 0.30). Use your broker's typical spread. |
| `--days 7` | Test only the last 7 days (faster). |
| `--refresh` | Download fresh prices now (normally it reuses data downloaded in the last 6 hours). |
| `--offline` | Use only the saved prices, no internet. |
| `--step 1h` | Test about **6 months** in 1-hour steps (report: `data\backtest_report_6m.html`). Before the last month, 1-hour candles stand in for 15-minute ones, so that part is an approximation; the report splits the two periods. |

Downloaded prices are saved in `data\backtest_cache\`. The free data source only gives about **one month** of
15-minute candles at a time, but each run adds the new candles to the saved ones. So if you run the backtest
every week or two, the tested period keeps getting longer and the results more meaningful.

## The rules it follows

- **BUY NOW / SELL NOW** plans: buy or sell at the open of the next 15-minute candle.
- **WAIT, then BUY / SELL** plans: only enter if, within 8 hours, price pokes through the plan's entry price
  and a 15-minute candle then closes back on the right side (exactly what the plan's steps tell you to do).
  The waiting order is cancelled if a candle closes beyond the stop, or if the Chief's direction changes.
- One trade at a time. No new trade while one is open.
- The trade ends at the **stop loss** or at **target 1**. If one candle touches both, it counts as the stop
  (the cautious assumption). If neither happens within 24 hours, it is closed at that moment's price.
- A cost of $0.30 is taken off on entry and again on exit (spread and slippage).
- Prices are COMEX gold **futures** (they run a few dollars above spot XAU/USD). Only the direction and the
  distances matter here, so this does not change the result much.

## How to read the numbers

- **R** ("risk unit"): 1R is the amount you lose when the stop is hit. A trade that makes twice what it
  risked is +2R. If you risk 1% of your account per trade, then +5R total is roughly +5% and −5R is −5%.
- **Win rate**: share of trades that made money. A low win rate can still be fine if winners are much bigger
  than losers; look at **Average R** and **Total R** together with it.
- **Average R per trade**: above 0 means the rules made money on average in this period, below 0 means they lost.
- **Max drawdown**: the worst fall from a previous high point, in R. Ask yourself whether you could sit
  through that many lost "R" in a row without giving up. In real trading, expect worse than this.
- **Longest losing streak**: the most losing trades in a row.
- **Split by BUY/SELL and by plan type**: shows whether, for example, only the "WAIT then" plans worked.
- **Agent 4-hour hit rate**: each agent's BUY/SELL call is checked 4 hours later. Right = price moved at least
  $3 its way, wrong = at least $3 against, smaller moves are ignored. This is the same rule as the dashboard's
  live track record. **About 50% is a coin flip.** Calls are made every 15 minutes, so many of them overlap and
  the true sample is much smaller than the number of calls suggests.

## Important

- **Past results do not guarantee future results.** Markets change; rules that worked last month may not
  work next month, and the other way round.
- **The sample is small.** About a month of data gives only a couple of dozen trades. With so few trades, luck
  dominates: a few trades going the other way would flip the result. Do not treat a good or bad result as
  proof either way until there are at least 100 trades (several months of runs).
- It ignores things a backtest cannot see: news spikes, your broker's real spread at that moment, and the
  fact that you may not be at the screen when a signal appears.
- Analysis only, not financial advice.
