# Trading Research Team (Claude Code subagents)

Four subagents that work as a pipeline for trading strategy research and
backtesting. **None of this executes real trades or gives investment
advice** — it's research/backtesting tooling only.

## The team

| Agent | Role | Tools |
|---|---|---|
| `strategy-researcher` | Turns a vague idea into a precise, testable spec | Read, Grep, Glob, WebSearch, WebFetch |
| `quant-backtester` | Writes/runs the backtest code, reports standard metrics | Read, Write, Edit, Bash |
| `auditor` | Reviews the backtest for bugs, look-ahead bias, overfitting | Read, Grep, Glob, Bash |
| `chart-analyst` | Visualizes equity curve, drawdown, trade distribution | Read, Write, Bash |

## Typical flow
1. **strategy-researcher** — "I have a hunch about X" → precise spec
   (universe, entry/exit rules, timeframe, rationale).
2. **quant-backtester** — runs the spec against `lib/backtester.py` +
   `lib/strategies.py`, reports return/Sharpe/drawdown/win-rate/trades.
3. **auditor** — checks the result for look-ahead bias, the
   boolean-shift dtype trap, overfitting, and unrealistic cost
   assumptions before you trust it.
4. **chart-analyst** — equity curve, drawdown, and trade-distribution
   charts once the numbers have passed review.

You can invoke any one directly (e.g. "have quant-backtester run a 20/50
SMA crossover on SPY") — they don't have to run in strict sequence, but
skipping straight from an idea to charts without the audit step is how
you end up trusting a buggy backtest.

## Shared engine: `lib/`
- `lib/backtester.py` — vectorized pandas backtest engine (no
  vectorbt/backtrader dependency). Handles long/flat and long/short,
  fees + slippage, close or next-bar-open execution, and computes total
  return / CAGR / Sharpe / max drawdown / win rate / trade log.
- `lib/strategies.py` — three example strategies (`sma_crossover`,
  `rsi_mean_reversion`, `bollinger_breakout`) as a template for adding
  your own.

**No live market data access from this environment.** Backtests run
against a CSV you supply (date + OHLCV columns, case-insensitive) or
`make_synthetic_data()` for a labeled-synthetic sanity check of the
engine itself.

## A known trap already fixed in this codebase
`pandas.Series.shift(1)` on a **boolean** Series casts to `object` dtype
(to hold the leading NaN), which silently breaks `~` negation — it does
Python bitwise-not on `bool` objects (`~True == -2`, always truthy)
instead of logical negation. `lib/strategies.py` and `auditor.md` both
call this out explicitly; if you write a new strategy with a shifted
boolean condition, cast back with `.fillna(False).astype(bool)` before
negating, and sanity-check signal counts.
