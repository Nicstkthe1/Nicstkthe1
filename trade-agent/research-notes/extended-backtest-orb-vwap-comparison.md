# Extended Backtest — SPY, 47 Trading Days (Jul 25 – Sep 30, 2025), Stock + Options

**Date run:** 2026-09-30
**Data:** Real SPY 5-min RTH bars via Webull connector, pulled in 3 paginated batches, deduplicated → 3,600 bars / 47 trading days (~10x the original 16-day sample).
**Options: still simulated**, same caveat as before — no real chain data available, Black-Scholes off the real underlying path with a flat assumed 16% IV. Treat P&L shape as directional, not tradeable.

## Results

| Strategy | Stock return | Stock Sharpe | Stock win rate | Stock trades | Options P&L (1 contract) | Options win rate |
|---|---|---|---|---|---|---|
| ORB (15-min range, 1.5x vol) | -1.22% | -2.43 | 50.0% | 26 | +$29.78 | 57.7% |
| VWAP mean-reversion (1.5σ entry) | -2.59% | -3.60 | 53.3% | 60 | +$205.04 | 65.0% |

## Read of this
With 3x the trade count, both strategies still lose money as stock positions but the win rates are much closer to 50-55% than the earlier 16-day sample suggested (which was mostly noise from too few trades). The options versions show small positive P&L here — options' convexity (limited loss on losers via a max-loss-is-premium floor, unlimited-ish upside on winners) can flip the sign relative to the underlying even when Sharpe is negative, but 26-60 trades is still a thin sample for either conclusion to be reliable, and the flat-IV assumption is doing real work here that a real chain wouldn't.

**VWAP mean-reversion trades ~2.3x more often than ORB** in this window (60 vs 26 signals over the same 47 days) and has moderately better stats on every metric — makes it the better candidate to refine further.

## Honest next steps, in order of value
1. **Get real options data** if at all possible (a data vendor, or the person's brokerage statements of actual past options fills) — the simulated-IV assumption is the biggest source of unreliability in the options numbers above.
2. **Push the stock-only Sharpe positive before layering options on** — options amplify whatever edge (or lack of edge) is already there; a strategy with negative Sharpe on the underlying is not fixed by adding leverage.
3. **Walk-forward test, not just in-sample**: split into e.g. first 30 days to tune entry_z/vol_mult, last 17 days to validate out-of-sample — this run tuned nothing yet, so it's a clean baseline, but any future parameter changes need this split to avoid overfitting.

## Files
- `/home/claude/trade-agent/data/SPY_M5_full.csv` — merged 47-day dataset
- `/home/claude/trade-agent/lib/strategies.py` — now has both `opening_range_breakout` and `vwap_mean_reversion`
- `/home/claude/trade-agent/run_full_comparison.py` — runs both strategies, stock + options, side by side
- `*_trades_full.csv` — per-strategy trade logs
