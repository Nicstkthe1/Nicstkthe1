"""Runs one cycle of the team. Invoked every few minutes by GitHub Actions.

    python -m trading_team run      # scan, decide, trade (or flatten after 15:45 ET)
    python -m trading_team flatten  # close everything now
    python -m trading_team report   # today's fills and P&L
"""

import logging
import os
import sys
from dataclasses import replace
from datetime import datetime

from . import analyst, risk
from .broker import ET, Broker
from .config import Settings

log = logging.getLogger("team")


def journal(line: str) -> None:
    """Log to the console and to the GitHub Actions run summary."""
    log.info(line)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(line + "\n\n")


def run(cfg: Settings, broker: Broker, now: datetime) -> None:
    mode = "LIVE" if cfg.live else "PAPER"
    journal(f"### {now:%Y-%m-%d %H:%M} ET | {mode} | orders {'ON' if cfg.trading_enabled else 'OFF (dry run)'}")

    if not broker.market_open():
        journal("Market closed, nothing to do.")
        return

    if now.time() >= cfg.flatten_at:
        n = broker.flatten_all() if cfg.trading_enabled else 0
        journal(f"**Flatten:** after {cfg.flatten_at} ET, closed {n} position(s). Day traders don't hold overnight.")
        return

    acct = broker.account_state(now)
    journal(
        f"Equity ${acct.equity:,.2f} | day P&L ${acct.day_pnl:+,.2f} | open {sorted(acct.open_symbols) or '-'} "
        f"| trades today {acct.trades_today}/{cfg.max_trades_per_day}"
    )

    gate = risk.can_open_new_trades(cfg, acct, now)
    if not gate.approved:
        journal(f"Risk manager: no new trades ({gate.reason}).")
        return

    symbols = sorted(set(cfg.universe) | {cfg.market_symbol})
    bars = broker.intraday_bars(symbols, now)
    if not analyst.market_is_healthy(bars.get(cfg.market_symbol, [])):
        journal(f"Analyst: {cfg.market_symbol} is below VWAP, so the market is weak. Standing aside.")
        return
    stats = broker.daily_stats(symbols, now)

    setups = []
    for sym in cfg.universe:
        if sym not in bars or sym not in stats:
            continue
        prev_close, avg_vol = stats[sym]
        setup, why = analyst.find_setup(sym, bars[sym], prev_close, avg_vol, now, cfg)
        if setup:
            setups.append(setup)
        else:
            log.debug("%s: %s", sym, why)
    setups.sort(key=lambda s: s.score, reverse=True)
    journal(f"Analyst: {len(setups)} setup(s): " + (", ".join(s.symbol for s in setups) or "none"))

    for setup in setups:
        # Re-check the account gate before each order; limits change as we trade.
        if not risk.can_open_new_trades(cfg, acct, now).approved:
            break
        decision = risk.size(cfg, acct, setup)
        if not decision.approved:
            journal(f"- {setup.symbol}: vetoed, {decision.reason}")
            continue
        line = (f"- **BUY {setup.symbol}** {decision.reason}; stop {setup.stop}, target {setup.target}. "
                f"Why: {setup.reason}")
        if cfg.trading_enabled:
            order_id = broker.buy_bracket(setup, decision.qty, now)
            journal(f"{line} (order {order_id})")
        else:
            journal(f"{line} (dry run, not sent)")
        acct = replace(
            acct,
            open_symbols=acct.open_symbols | {setup.symbol},
            open_notional=acct.open_notional + decision.qty * setup.entry,
            symbols_traded_today=acct.symbols_traded_today | {setup.symbol},
            trades_today=acct.trades_today + 1,
        )


def report(broker: Broker, now: datetime) -> None:
    acct = broker.account_state(now)
    journal(f"## Daily report {now:%Y-%m-%d}\nEquity ${acct.equity:,.2f}, day P&L **${acct.day_pnl:+,.2f}**")
    fills = broker.todays_fills(now)
    if not fills:
        journal("No trades today.")
    for t, sym, side, qty, px in fills:
        journal(f"- {t:%H:%M} {side.upper()} {qty:g} {sym} @ {px:.2f}")


def main(argv=None) -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(message)s")
    cmd = (argv or sys.argv[1:] or ["run"])[0]
    cfg = Settings()
    broker = Broker(cfg)
    now = datetime.now(ET)
    if cmd == "run":
        run(cfg, broker, now)
    elif cmd == "flatten":
        journal(f"Manual flatten: closed {broker.flatten_all()} position(s).")
    elif cmd == "report":
        report(broker, now)
    else:
        print(__doc__)
        return 2
    return 0
