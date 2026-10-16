# ORB Strategy with Options Overlay — SPY, First Run

**Date run:** 2026-09-30
**Underlying data:** same real SPY 5-min bars as the stock backtest (2025-09-09 to 2025-09-30, 16 trading days).
**Option data: SIMULATED, not real.** No connected tool provides historical options chain data (Webull's bar-history endpoint explicitly excludes options; the option order tools create real, user-confirmed trades, not backtest data). Option prices are modeled with Black-Scholes off the real underlying path, using an assumed constant 16% implied volatility. This captures the shape/leverage of an options approach but NOT real bid/ask spread, IV skew, or IV crush around news — treat as a rough sketch, not a tradeable estimate.

## Setup
Same 16 ORB signals as the stock version (see `orb-spy-backtest-results.md`), but each trade buys an ATM call, 7 calendar days to expiry at entry, instead of buying the stock. Exit uses the same bar as the stock version (range-midpoint break or 15:45 ET flatten) — option is sold-to-close at its modeled price on that bar.

## Results (1 contract per trade, $0.65/contract fees each way)
- Total net P&L: **-$376.75**
- Win rate: **18.8%** (same trades lose money as the stock version — same signal, same direction)
- Avg |underlying move| per trade: 0.17% vs avg |option move|: 9.65% → **~56x leverage ratio**

## Read of this
The options version didn't fix the strategy — it amplified it. Same losing trades, same 18.8% win rate, but each loss is ~50-90x bigger in percentage terms because of leverage + time decay eating into the small, choppy underlying moves the ORB entries are catching. This is the standard failure mode of running a low-win-rate, small-edge signal through short-dated options: theta and leverage punish the frequent small losses much harder than they reward the rare big win.

**Before trusting this shape at all:** get real IV/chain data (this used one assumed IV for every trade, not the market's actual smile) and a much larger sample — 16 trades is not enough to separate "bad strategy" from "bad luck."

## Files
- `/home/claude/trade-agent/lib/options.py` — Black-Scholes pricer + trade simulator
- `/home/claude/trade-agent/run_orb_options_backtest.py`
- `/home/claude/trade-agent/data/orb_options_trades.csv`
