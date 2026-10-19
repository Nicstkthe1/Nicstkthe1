# ORB (Opening Range Breakout) — SPY, 5-min bars, RTH — First Run

**Date run:** 2026-09-30
**Data:** Real SPY 5-min bars via Webull connector, 2025-09-09 to 2025-09-30 (16 trading days, 1200 bars — capped by API's per-call bar limit, so this is a small/noisy sample, not a validated result).

## Strategy
Long-only ORB: range = high/low of first 15 min of RTH each day. Enter long
on a close above the range high with volume ≥ 1.5x that time-of-day bucket's
expanding average (falls back to same-session average early in the window —
a known limitation with <20 days of history). Exit on close back below the
range midpoint, or flatten by 15:45 ET.

## Results (after fixing a state-machine bug, see below)
- Total return: **-1.96%**
- Annualized Sharpe: **-9.32**
- Max drawdown: **-1.97%**
- Win rate: **18.8%** (3 of 16 trades)
- Trades: 16

**Read of this**: with only 16 trades over 16 days, this is not a green
light or a red light — it's too small a sample to trust. The strategy as
specified loses money and has a low win rate in this window; the honest
next step is more data (weeks→months of bars, pulled in batches given the
API's per-call cap) before drawing any conclusion, not tuning parameters
against this one sample.

## Bug found and fixed during review (auditor function)
Original state machine checked `entries` before `exits` every bar. Because
both signals are level-based (can stay True for multiple consecutive bars),
an active breakout signal could override the 15:45 end-of-day flatten and
silently carry a position overnight — invisible in the return numbers alone,
only visible by inspecting individual trade timestamps. Fixed by making
entries only fire while flat and exits only fire while in a position, so an
active exit always wins.

## Project structure built
- `/home/claude/trade-agent/lib/backtester.py` — vectorized pandas engine (no lookahead: position shifted by 1 bar before applying returns; fees+slippage charged per position change)
- `/home/claude/trade-agent/lib/strategies.py` — `opening_range_breakout()`
- `/home/claude/trade-agent/.claude/agents/` — strategy-researcher, quant-backtester, auditor, chart-analyst subagent definitions
- `/home/claude/trade-agent/data/SPY_M5.csv` — raw bars, `orb_trades.csv` / `orb_equity.csv` — outputs

## Next steps
1. Pull more history (loop the Webull call across date ranges) to get a
   real sample size — 16 trades tells us almost nothing.
2. Test the other two strategy ideas (VWAP mean-reversion, gap fade) on the
   same data for comparison.
3. Have the chart-analyst agent render the equity/drawdown curves once
   sample size is adequate.
