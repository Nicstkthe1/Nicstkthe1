"""
strategies.py
=============
Example strategy signal functions for the quant-backtester agent. Each
takes a DataFrame with at least a 'close' column and returns
(entries, exits) as boolean pd.Series aligned to df.index, suitable for
backtester.run_backtest().

Add new strategies here following the same (df, **params) -> (entries, exits)
signature and register them in STRATEGY_REGISTRY.
"""

import numpy as np
import pandas as pd


def sma_crossover(df: pd.DataFrame, fast: int = 20, slow: int = 50):
    """
    Classic moving-average crossover: go long when the fast SMA crosses
    above the slow SMA, exit when it crosses back below.
    """
    fast_ma = df["close"].rolling(fast).mean()
    slow_ma = df["close"].rolling(slow).mean()

    above = fast_ma > slow_ma
    # NOTE: bool Series.shift(1) casts to object dtype (to hold the
    # leading NaN), which silently breaks `~` (bitwise-not on Python bool
    # objects, not logical negation). Must re-cast to bool after fillna.
    prev_above = above.shift(1).fillna(False).astype(bool)
    entries = above & (~prev_above)
    exits = (~above) & prev_above
    return entries.fillna(False), exits.fillna(False)


def rsi_mean_reversion(df: pd.DataFrame, period: int = 14, oversold: float = 30, overbought: float = 70):
    """
    Mean-reversion: go long when RSI crosses up out of oversold territory,
    exit when RSI crosses up through the overbought level.
    """
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    was_oversold = rsi.shift(1) < oversold
    entries = (rsi >= oversold) & was_oversold
    was_overbought = rsi.shift(1) < overbought
    exits = (rsi >= overbought) & was_overbought

    return entries.fillna(False), exits.fillna(False)


def bollinger_breakout(df: pd.DataFrame, window: int = 20, n_std: float = 2.0):
    """
    Breakout: go long when price closes above the upper Bollinger Band,
    exit when price closes back below the middle band (the rolling mean).
    """
    mid = df["close"].rolling(window).mean()
    std = df["close"].rolling(window).std()
    upper = mid + n_std * std

    entries = (df["close"] > upper) & (df["close"].shift(1) <= upper.shift(1))
    exits = (df["close"] < mid) & (df["close"].shift(1) >= mid.shift(1))
    return entries.fillna(False), exits.fillna(False)


STRATEGY_REGISTRY = {
    "sma_crossover": sma_crossover,
    "rsi_mean_reversion": rsi_mean_reversion,
    "bollinger_breakout": bollinger_breakout,
}
