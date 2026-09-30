"""All tunable settings, read from environment variables with safe defaults."""

import os
from dataclasses import dataclass, field
from datetime import time


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


# Liquid large caps and ETFs only: tight spreads, no penny stocks, hard to manipulate.
DEFAULT_UNIVERSE = (
    "AAPL,MSFT,NVDA,AMZN,META,GOOGL,TSLA,AMD,AVGO,NFLX,CRM,ORCL,ADBE,INTC,MU,"
    "QCOM,UBER,SHOP,PLTR,COIN,JPM,BAC,XOM,CVX,LLY,UNH,COST,WMT,DIS,BA,"
    "QQQ,SPY,IWM,XLF,XLE,SMH"
)


@dataclass(frozen=True)
class Settings:
    # --- Safety switches -------------------------------------------------
    # Master kill switch. false = the team analyses and logs but sends no orders.
    trading_enabled: bool = field(default_factory=lambda: _bool("TRADING_ENABLED", True))
    # false = Alpaca paper account (fake money). true = real money.
    live: bool = field(default_factory=lambda: _bool("ALPACA_LIVE", False))

    # --- Money ------------------------------------------------------------
    budget: float = field(default_factory=lambda: _float("BUDGET", 1000.0))
    risk_per_trade_pct: float = field(default_factory=lambda: _float("RISK_PER_TRADE_PCT", 1.0))
    max_position_pct: float = field(default_factory=lambda: _float("MAX_POSITION_PCT", 40.0))
    daily_loss_limit_pct: float = field(default_factory=lambda: _float("DAILY_LOSS_LIMIT_PCT", 3.0))
    max_open_positions: int = field(default_factory=lambda: _int("MAX_OPEN_POSITIONS", 2))
    max_trades_per_day: int = field(default_factory=lambda: _int("MAX_TRADES_PER_DAY", 3))
    respect_pdt: bool = field(default_factory=lambda: _bool("RESPECT_PDT", True))

    # --- Strategy (opening-range breakout momentum, long only) ------------
    universe: tuple = field(
        default_factory=lambda: tuple(
            s.strip().upper() for s in os.getenv("UNIVERSE", DEFAULT_UNIVERSE).split(",") if s.strip()
        )
    )
    market_symbol: str = "SPY"
    opening_range_minutes: int = 15
    min_price: float = 5.0
    min_relative_volume: float = field(default_factory=lambda: _float("MIN_RELATIVE_VOLUME", 1.5))
    max_stop_pct: float = 2.5  # skip setups whose stop is further than this from entry
    min_stop_pct: float = 0.3  # stops tighter than this get shaken out by noise
    max_chase_pct: float = 1.5  # skip if price already ran this far past the breakout level
    reward_risk: float = field(default_factory=lambda: _float("REWARD_RISK", 2.0))

    # --- Clock (US/Eastern) ----------------------------------------------
    entry_start: time = time(9, 45)
    entry_end: time = time(11, 30)
    flatten_at: time = time(15, 45)
