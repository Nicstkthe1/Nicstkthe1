"""Risk manager: sizes every trade and can veto it. Its rules override the analyst."""

import math
from dataclasses import dataclass
from datetime import datetime

from .analyst import Setup
from .config import Settings


@dataclass(frozen=True)
class AccountState:
    equity: float
    day_pnl: float  # equity change since yesterday's close
    open_symbols: frozenset
    open_notional: float
    symbols_traded_today: frozenset
    trades_today: int
    daytrade_count: int
    trading_blocked: bool


@dataclass(frozen=True)
class Decision:
    approved: bool
    qty: int = 0
    reason: str = ""


def budget(cfg: Settings, acct: AccountState) -> float:
    """Never trade more than the configured budget, or the account's equity if smaller."""
    return min(cfg.budget, acct.equity)


def daily_loss_hit(cfg: Settings, acct: AccountState) -> bool:
    return acct.day_pnl <= -budget(cfg, acct) * cfg.daily_loss_limit_pct / 100


def can_open_new_trades(cfg: Settings, acct: AccountState, now: datetime) -> Decision:
    """Account-level checks that apply before looking at any individual setup."""
    if acct.trading_blocked:
        return Decision(False, reason="broker says trading is blocked on this account")
    if not (cfg.entry_start <= now.time() < cfg.entry_end):
        return Decision(False, reason=f"outside entry window {cfg.entry_start}-{cfg.entry_end} ET")
    if daily_loss_hit(cfg, acct):
        return Decision(False, reason=f"daily loss limit hit (day P&L {acct.day_pnl:.2f})")
    if acct.trades_today >= cfg.max_trades_per_day:
        return Decision(False, reason=f"max {cfg.max_trades_per_day} trades per day reached")
    if len(acct.open_symbols) >= cfg.max_open_positions:
        return Decision(False, reason=f"max {cfg.max_open_positions} open positions reached")
    if cfg.respect_pdt and acct.equity < 25_000 and acct.daytrade_count >= 3:
        return Decision(False, reason="pattern-day-trader limit: 3 day trades in 5 days used")
    return Decision(True)


def size(cfg: Settings, acct: AccountState, setup: Setup) -> Decision:
    """Decide how many shares (whole shares only; brackets can't be fractional)."""
    if setup.symbol in acct.open_symbols:
        return Decision(False, reason="already holding it")
    if setup.symbol in acct.symbols_traded_today:
        return Decision(False, reason="already traded today, no revenge re-entries")
    if setup.risk_per_share <= 0:
        return Decision(False, reason="invalid stop")

    b = budget(cfg, acct)
    risk_dollars = b * cfg.risk_per_trade_pct / 100
    by_risk = math.floor(risk_dollars / setup.risk_per_share)
    by_position_cap = math.floor(b * cfg.max_position_pct / 100 / setup.entry)
    by_budget_left = math.floor(max(0.0, b - acct.open_notional) / setup.entry)
    qty = min(by_risk, by_position_cap, by_budget_left)
    if qty < 1:
        return Decision(
            False,
            reason=f"can't afford 1 share within limits (risk ${risk_dollars:.2f}, "
            f"budget left ${b - acct.open_notional:.2f})",
        )
    return Decision(
        True,
        qty,
        f"{qty} sh @ ~{setup.entry:.2f}, risking ${qty * setup.risk_per_share:.2f} "
        f"({qty * setup.risk_per_share / b * 100:.2f}% of budget)",
    )
