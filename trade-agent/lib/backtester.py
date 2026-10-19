"""
backtester.py
=============
A lightweight, dependency-minimal vectorized backtesting engine built on
pandas/numpy for the quant-backtester agent. No vectorbt/backtrader
dependency required (vectorbt has had plotly-version conflicts in some
environments, and backtrader's event-driven loop is unnecessarily slow
for simple signal-based strategies), but the API is intentionally similar
to vectorbt's Portfolio.from_signals style.

DATA SOURCE / ASSUMPTIONS
--------------------------
- This engine does NOT fetch live market data itself. Supply a CSV (or a
  pandas DataFrame) with at least: a datetime index/column and a 'close'
  column. 'open', 'high', 'low', 'volume' are optional but used for
  realism (e.g. next-bar-open execution) if present.
- All backtests are LONG/FLAT (or LONG/SHORT if allow_short=True) on a
  SINGLE instrument. No portfolio-level multi-asset allocation.
- Default execution: signals generated on bar t execute at bar t's close
  (a common simplification). Set execution='next_open' for a more
  realistic next-bar-open fill if your data has an 'open' column.
- Fees and slippage are modeled as a flat percentage per trade (charged
  on both entry and exit) via `fee_pct` and `slippage_pct`.
- No margin, no borrowing cost modeling, no intraday-bar assumptions --
  works on whatever bar frequency your CSV is in (daily by default).

USAGE
-----
    from backtester import load_csv, run_backtest, summarize

    df = load_csv("SPY.csv")
    entries, exits = my_strategy_fn(df)           # boolean pd.Series
    result = run_backtest(df, entries, exits, initial_capital=100_000)
    print(summarize(result))
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------

def load_csv(path: str, date_col: str = "date") -> pd.DataFrame:
    """
    Load OHLCV data from a CSV file.

    Expects a date column (default name 'date') parseable by pandas, plus
    a 'close' column at minimum. Column names are lower-cased and stripped
    so 'Close', ' Close ', 'CLOSE' all match.

    Returns a DataFrame sorted ascending by date, indexed by date.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    if date_col not in df.columns:
        for alt in ("date", "datetime", "timestamp", "time"):
            if alt in df.columns:
                date_col = alt
                break
        else:
            raise ValueError(
                f"No date column found. Looked for '{date_col}', "
                f"'date', 'datetime', 'timestamp', 'time'. "
                f"Columns present: {list(df.columns)}"
            )

    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col).sort_index()

    if "close" not in df.columns:
        raise ValueError(
            f"No 'close' column found. Columns present: {list(df.columns)}"
        )

    return df


def make_synthetic_data(
    n_days: int = 1000,
    start_price: float = 100.0,
    annual_drift: float = 0.08,
    annual_vol: float = 0.20,
    seed: int = 42,
    start_date: str = "2020-01-01",
) -> pd.DataFrame:
    """
    Generate synthetic daily OHLCV data via geometric Brownian motion, for
    demoing/testing the engine when you don't have real market data handy.
    NOT a substitute for real backtesting data -- GBM has none of the fat
    tails, volatility clustering, or regime shifts real markets have.
    """
    rng = np.random.default_rng(seed)
    dt = 1 / 252
    mu, sigma = annual_drift, annual_vol

    shocks = rng.normal((mu - 0.5 * sigma**2) * dt, sigma * np.sqrt(dt), n_days)
    close = start_price * np.exp(np.cumsum(shocks))

    dates = pd.bdate_range(start=start_date, periods=n_days)
    noise = rng.normal(0, sigma * np.sqrt(dt) * 0.5, n_days)
    open_ = close * (1 - noise)
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.002, n_days)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.002, n_days)))
    volume = rng.integers(1_000_000, 5_000_000, n_days)

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )
    df.index.name = "date"
    return df


# --------------------------------------------------------------------------
# Core simulation
# --------------------------------------------------------------------------

@dataclass
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    positions: pd.Series          # 1 = long, -1 = short, 0 = flat
    trades: pd.DataFrame          # one row per closed trade
    initial_capital: float
    fee_pct: float
    slippage_pct: float
    data_start: pd.Timestamp
    data_end: pd.Timestamp
    n_bars: int
    metadata: dict = field(default_factory=dict)


def run_backtest(
    df: pd.DataFrame,
    entries: pd.Series,
    exits: pd.Series,
    initial_capital: float = 100_000.0,
    fee_pct: float = 0.0005,        # 5 bps per side
    slippage_pct: float = 0.0005,   # 5 bps per side
    allow_short: bool = False,
    short_entries: Optional[pd.Series] = None,
    short_exits: Optional[pd.Series] = None,
    execution: str = "close",       # 'close' or 'next_open'
    position_size: float = 1.0,     # fraction of equity to deploy
) -> BacktestResult:
    """
    Vectorized long/flat (or long/short) backtest from boolean entry/exit
    signal series aligned to df's index.

    entries / exits: boolean pd.Series, same index as df. entries[t]=True
        means "go long as of bar t"; exits[t]=True means "close the long
        position as of bar t". If both are True on the same bar, exit is
        applied first, then entry (flat-then-re-enter).

    allow_short: if True, also supply short_entries / short_exits (same
        semantics for opening/closing a short). Long and short positions
        are mutually exclusive at any point in time.

    execution: 'close' fills signals at the same bar's close (look-ahead-
        free ONLY if the signal itself only uses information available by
        that close). 'next_open' fills at the following bar's open.

    position_size: fraction of current equity to allocate when entering a
        position (1.0 = fully invested).
    """
    df = df.copy()
    entries = entries.reindex(df.index).fillna(False).astype(bool)
    exits = exits.reindex(df.index).fillna(False).astype(bool)

    if allow_short:
        if short_entries is None or short_exits is None:
            raise ValueError("allow_short=True requires short_entries and short_exits")
        short_entries = short_entries.reindex(df.index).fillna(False).astype(bool)
        short_exits = short_exits.reindex(df.index).fillna(False).astype(bool)

    if execution not in ("close", "next_open"):
        raise ValueError("execution must be 'close' or 'next_open'")
    if execution == "next_open" and "open" not in df.columns:
        raise ValueError("execution='next_open' requires an 'open' column in df")

    if execution == "close":
        fill_price = df["close"]
    else:
        fill_price = df["open"].shift(-1)
        fill_price.iloc[-1] = df["close"].iloc[-1]

    n = len(df)
    position = np.zeros(n, dtype=int)
    cash_arr = np.zeros(n, dtype=float)
    shares_arr = np.zeros(n, dtype=float)
    equity = np.zeros(n, dtype=float)

    trades = []
    cur_pos = 0
    cur_shares = 0.0
    cur_cash = initial_capital
    entry_price = None
    entry_date = None
    entry_idx = None

    ent = entries.values
    ext = exits.values
    s_ent = short_entries.values if allow_short else None
    s_ext = short_exits.values if allow_short else None
    fills = fill_price.values
    closes = df["close"].values
    idx = df.index

    for t in range(n):
        px = fills[t]

        # 1. process exits first (flat-then-re-enter semantics)
        if cur_pos == 1 and ext[t]:
            exit_px = px * (1 - slippage_pct)
            proceeds = cur_shares * exit_px * (1 - fee_pct)
            cur_cash += proceeds
            trades.append({
                "side": "long",
                "entry_date": entry_date,
                "exit_date": idx[t],
                "entry_price": entry_price,
                "exit_price": exit_px,
                "shares": cur_shares,
                "pnl": proceeds - (cur_shares * entry_price),
                "return_pct": (exit_px / entry_price) - 1,
                "bars_held": t - entry_idx,
            })
            cur_shares = 0.0
            cur_pos = 0
            entry_price = None

        if allow_short and cur_pos == -1 and s_ext[t]:
            # Short entry already credited abs(cur_shares)*entry_price*(1-fee)
            # proceeds into cur_cash. Closing means buying back the shares.
            exit_px = px * (1 + slippage_pct)
            cost_to_cover = abs(cur_shares) * exit_px * (1 + fee_pct)
            entry_proceeds = abs(cur_shares) * entry_price * (1 - fee_pct)
            pnl = entry_proceeds - cost_to_cover
            cur_cash -= cost_to_cover
            trades.append({
                "side": "short",
                "entry_date": entry_date,
                "exit_date": idx[t],
                "entry_price": entry_price,
                "exit_price": exit_px,
                "shares": cur_shares,
                "pnl": pnl,
                "return_pct": (entry_price / exit_px) - 1,
                "bars_held": t - entry_idx,
            })
            cur_shares = 0.0
            cur_pos = 0
            entry_price = None

        # 2. process entries
        if cur_pos == 0 and ent[t]:
            entry_px = px * (1 + slippage_pct)
            deploy = cur_cash * position_size
            n_shares = (deploy * (1 - fee_pct)) / entry_px
            cur_cash -= n_shares * entry_px * (1 + fee_pct)
            cur_shares = n_shares
            cur_pos = 1
            entry_price = entry_px
            entry_date = idx[t]
            entry_idx = t

        elif allow_short and cur_pos == 0 and s_ent[t]:
            entry_px = px * (1 - slippage_pct)
            deploy = cur_cash * position_size
            n_shares = deploy / entry_px
            cur_cash += n_shares * entry_px * (1 - fee_pct)  # short-sale proceeds, net of fee
            cur_shares = -n_shares
            cur_pos = -1
            entry_price = entry_px
            entry_date = idx[t]
            entry_idx = t

        position[t] = cur_pos
        cash_arr[t] = cur_cash
        shares_arr[t] = cur_shares
        equity[t] = cur_cash + cur_shares * closes[t] if cur_pos != 0 else cur_cash

    equity_curve = pd.Series(equity, index=idx, name="equity")
    returns = equity_curve.pct_change().fillna(0.0)
    positions_s = pd.Series(position, index=idx, name="position")
    trades_df = pd.DataFrame(trades)

    return BacktestResult(
        equity_curve=equity_curve,
        returns=returns,
        positions=positions_s,
        trades=trades_df,
        initial_capital=initial_capital,
        fee_pct=fee_pct,
        slippage_pct=slippage_pct,
        data_start=idx[0],
        data_end=idx[-1],
        n_bars=n,
    )


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def _infer_periods_per_year(index: pd.DatetimeIndex) -> float:
    """Rough inference of bar frequency for annualization (defaults to daily/252)."""
    if len(index) < 2:
        return 252.0
    median_days = np.median(np.diff(index.values).astype("timedelta64[D]").astype(float))
    if median_days <= 0:
        return 252.0
    return 365.25 / median_days


def compute_metrics(result: BacktestResult) -> dict:
    """
    Compute the standard set of backtest metrics: total return, CAGR,
    Sharpe ratio, max drawdown, win rate, number of trades.
    """
    eq = result.equity_curve
    rets = result.returns
    trades = result.trades

    total_return = eq.iloc[-1] / result.initial_capital - 1

    periods_per_year = _infer_periods_per_year(eq.index)
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years > 0 and eq.iloc[-1] > 0:
        cagr = (eq.iloc[-1] / result.initial_capital) ** (1 / n_years) - 1
    else:
        cagr = np.nan

    if rets.std() > 0:
        sharpe = (rets.mean() / rets.std()) * np.sqrt(periods_per_year)
    else:
        sharpe = np.nan

    running_max = eq.cummax()
    drawdown = eq / running_max - 1
    max_drawdown = drawdown.min()

    n_trades = len(trades)
    if n_trades > 0:
        win_rate = (trades["pnl"] > 0).mean()
        avg_win = trades.loc[trades["pnl"] > 0, "pnl"].mean() if (trades["pnl"] > 0).any() else 0.0
        avg_loss = trades.loc[trades["pnl"] <= 0, "pnl"].mean() if (trades["pnl"] <= 0).any() else 0.0
        avg_bars_held = trades["bars_held"].mean()
        gross_profit = trades.loc[trades["pnl"] > 0, "pnl"].sum()
        gross_loss = -trades.loc[trades["pnl"] <= 0, "pnl"].sum()
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
    else:
        win_rate = np.nan
        avg_win = np.nan
        avg_loss = np.nan
        avg_bars_held = np.nan
        profit_factor = np.nan

    return {
        "total_return_pct": total_return * 100,
        "cagr_pct": cagr * 100 if not np.isnan(cagr) else np.nan,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_drawdown * 100,
        "win_rate_pct": win_rate * 100 if not np.isnan(win_rate) else np.nan,
        "num_trades": n_trades,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "avg_bars_held": avg_bars_held,
        "profit_factor": profit_factor,
        "final_equity": eq.iloc[-1],
        "data_start": str(result.data_start.date()),
        "data_end": str(result.data_end.date()),
        "n_bars": result.n_bars,
        "fee_pct_per_side": result.fee_pct * 100,
        "slippage_pct_per_side": result.slippage_pct * 100,
    }


def summarize(result: BacktestResult) -> str:
    """Human-readable summary block of backtest metrics."""
    m = compute_metrics(result)
    lines = [
        "=" * 50,
        "BACKTEST SUMMARY",
        "=" * 50,
        f"Data range        : {m['data_start']} to {m['data_end']}  ({m['n_bars']} bars)",
        f"Costs assumed     : {m['fee_pct_per_side']:.3f}% fee + {m['slippage_pct_per_side']:.3f}% slippage per side",
        "-" * 50,
        f"Total Return      : {m['total_return_pct']:.2f}%",
        f"CAGR              : {m['cagr_pct']:.2f}%",
        f"Sharpe Ratio      : {m['sharpe_ratio']:.2f}",
        f"Max Drawdown      : {m['max_drawdown_pct']:.2f}%",
        f"Win Rate          : {m['win_rate_pct']:.2f}%",
        f"Number of Trades  : {m['num_trades']}",
        f"Profit Factor     : {m['profit_factor']:.2f}" if np.isfinite(m['profit_factor']) else "Profit Factor     : inf",
        f"Avg Bars Held     : {m['avg_bars_held']:.1f}" if not np.isnan(m['avg_bars_held']) else "Avg Bars Held     : n/a",
        f"Final Equity      : ${m['final_equity']:,.2f}",
        "=" * 50,
    ]
    return "\n".join(lines)
