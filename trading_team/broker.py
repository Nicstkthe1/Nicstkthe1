"""Trader: the only module that talks to the broker (Alpaca)."""

import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, OrderStatus, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest, StopLossRequest, TakeProfitRequest

from .analyst import Bar, Setup
from .config import Settings
from .risk import AccountState

ET = ZoneInfo("America/New_York")
ORDER_PREFIX = "tt-"
log = logging.getLogger("trader")


class Broker:
    def __init__(self, cfg: Settings):
        if cfg.live:
            key, secret = os.environ["ALPACA_LIVE_KEY_ID"], os.environ["ALPACA_LIVE_SECRET_KEY"]
        else:
            key, secret = os.environ["ALPACA_PAPER_KEY_ID"], os.environ["ALPACA_PAPER_SECRET_KEY"]
        self.cfg = cfg
        self.trading = TradingClient(key, secret, paper=not cfg.live)
        self.data = StockHistoricalDataClient(key, secret)

    # --- Clock & account -------------------------------------------------
    def market_open(self) -> bool:
        return self.trading.get_clock().is_open

    def account_state(self, now: datetime) -> AccountState:
        acct = self.trading.get_account()
        positions = self.trading.get_all_positions()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        todays = self.trading.get_orders(
            GetOrdersRequest(status=QueryOrderStatus.ALL, after=midnight, limit=500, nested=False)
        )
        entries = [
            o for o in todays
            if (o.client_order_id or "").startswith(ORDER_PREFIX)
            and o.side == OrderSide.BUY
            and o.status not in (OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED)
        ]
        equity = float(acct.equity)
        return AccountState(
            equity=equity,
            day_pnl=equity - float(acct.last_equity),
            open_symbols=frozenset(p.symbol for p in positions),
            open_notional=sum(abs(float(p.market_value)) for p in positions),
            symbols_traded_today=frozenset(o.symbol for o in entries),
            trades_today=len(entries),
            daytrade_count=int(acct.daytrade_count or 0),
            trading_blocked=bool(acct.trading_blocked or acct.account_blocked),
        )

    # --- Market data -----------------------------------------------------
    def intraday_bars(self, symbols, now: datetime) -> dict:
        """Completed 5-minute regular-session bars for today, keyed by symbol."""
        session_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        resp = self.data.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=list(symbols),
                timeframe=TimeFrame(5, TimeFrameUnit.Minute),
                start=session_open,
                end=now,
                feed=DataFeed.IEX,
            )
        )
        out = {}
        for sym, raw in resp.data.items():
            bars = [
                Bar(b.timestamp.astimezone(ET), b.open, b.high, b.low, b.close, b.volume)
                for b in raw
            ]
            # Drop the bar that is still forming.
            out[sym] = [b for b in bars if b.t + timedelta(minutes=5) <= now]
        return out

    def daily_stats(self, symbols, now: datetime) -> dict:
        """{symbol: (previous close, 20-day average volume)}."""
        resp = self.data.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=list(symbols),
                timeframe=TimeFrame.Day,
                start=now - timedelta(days=40),
                end=now.replace(hour=0, minute=0, second=0, microsecond=0),
                adjustment=Adjustment.SPLIT,
                feed=DataFeed.IEX,
            )
        )
        out = {}
        for sym, raw in resp.data.items():
            prior = [b for b in raw if b.timestamp.astimezone(ET).date() < now.date()][-20:]
            if prior:
                out[sym] = (prior[-1].close, sum(b.volume for b in prior) / len(prior))
        return out

    # --- Orders ------------------------------------------------------------
    def buy_bracket(self, setup: Setup, qty: int, now: datetime) -> str:
        """Market entry with a take-profit and a stop-loss held at the broker.

        GTC so the protective stop survives even if the end-of-day flatten run is late.
        """
        order = self.trading.submit_order(
            MarketOrderRequest(
                symbol=setup.symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=setup.target),
                stop_loss=StopLossRequest(stop_price=setup.stop),
                client_order_id=f"{ORDER_PREFIX}{setup.symbol}-{now:%Y%m%d%H%M%S}",
            )
        )
        return str(order.id)

    def flatten_all(self) -> int:
        """Cancel every open order and close every position at market."""
        closed = self.trading.close_all_positions(cancel_orders=True)
        return len(closed or [])

    def todays_fills(self, now: datetime) -> list:
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        orders = self.trading.get_orders(
            GetOrdersRequest(status=QueryOrderStatus.CLOSED, after=midnight, limit=500, nested=True)
        )
        fills = []
        for o in orders:
            for leg in [o, *(o.legs or [])]:
                if leg.filled_at and float(leg.filled_qty or 0) > 0:
                    fills.append(
                        (leg.filled_at.astimezone(ET), leg.symbol, leg.side.value,
                         float(leg.filled_qty), float(leg.filled_avg_price))
                    )
        return sorted(fills)
