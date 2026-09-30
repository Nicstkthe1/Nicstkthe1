from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from trading_team import analyst, risk
from trading_team.analyst import Bar, Setup
from trading_team.config import Settings
from trading_team.main import run

ET = ZoneInfo("America/New_York")
DAY = datetime(2026, 9, 30, tzinfo=ET)


def at(h, m):
    return DAY.replace(hour=h, minute=m)


def make_bars(prices, volume=100_000, rng=0.2):
    """5-min bars from 9:30; each price is a close, with a small high/low range."""
    return [
        Bar(at(9, 30) + timedelta(minutes=5 * i), p, p + rng, p - rng, p, volume)
        for i, p in enumerate(prices)
    ]


def breakout_bars():
    # Opening range 100.2 high / 99.3 low, then a clean push to 100.9.
    bars = make_bars([100.0, 99.5, 100.0, 100.3, 100.9])
    bars[1] = replace(bars[1], low=99.3)
    return bars


CFG = Settings()


def flat_acct(**kw):
    base = dict(equity=5000, day_pnl=0, open_symbols=frozenset(), open_notional=0,
                symbols_traded_today=frozenset(), trades_today=0, daytrade_count=0,
                trading_blocked=False)
    base.update(kw)
    return risk.AccountState(**base)


# --- Analyst ---------------------------------------------------------------

def test_breakout_found():
    setup, why = analyst.find_setup("AAPL", breakout_bars(), 99.0, 2_000_000, at(9, 55), CFG)
    assert setup, why
    assert setup.stop == pytest.approx(99.3)
    assert setup.target == pytest.approx(100.9 + 2 * (100.9 - 99.3), abs=0.01)


def test_no_breakout_inside_range():
    bars = make_bars([100.0, 99.5, 100.0, 99.9, 100.1])
    setup, why = analyst.find_setup("AAPL", bars, 99.0, 2_000_000, at(9, 55), CFG)
    assert setup is None and "no breakout" in why


def test_rejects_red_day():
    setup, why = analyst.find_setup("AAPL", breakout_bars(), 105.0, 2_000_000, at(9, 55), CFG)
    assert setup is None and "red" in why


def test_rejects_low_volume():
    setup, why = analyst.find_setup("AAPL", breakout_bars(), 99.0, 500_000_000, at(9, 55), CFG)
    assert setup is None and "relative volume" in why


def test_rejects_chasing():
    bars = make_bars([100.0, 99.5, 100.0, 100.3, 103.0])
    setup, why = analyst.find_setup("AAPL", bars, 99.0, 2_000_000, at(9, 55), CFG)
    assert setup is None and "extended" in why


def test_rejects_penny_stock():
    bars = make_bars([2.0, 1.98, 2.0, 2.01, 2.03], rng=0.005)
    setup, why = analyst.find_setup("TOVX", bars, 1.9, 1000, at(9, 55), CFG)
    assert setup is None and "minimum" in why


def test_market_filter():
    assert analyst.market_is_healthy(make_bars([500, 501, 502, 503]))
    assert not analyst.market_is_healthy(make_bars([503, 502, 501, 500]))


# --- Risk manager -------------------------------------------------------------

SETUP = Setup("AAPL", entry=100.0, stop=99.0, target=102.0, relative_volume=3, score=3, reason="t")


def test_size_is_capped_by_risk_and_position_size():
    d = risk.size(CFG, flat_acct(), SETUP)
    # $1000 budget: 1% risk = $10 / $1 stop = 10 sh, but 40% cap = $400 -> 4 sh.
    assert d.approved and d.qty == 4


def test_budget_is_capped_by_small_equity():
    d = risk.size(CFG, flat_acct(equity=300), SETUP)
    # budget = $300 -> $3 risk -> 3 sh; 40% cap = $120 -> 1 sh.
    assert d.approved and d.qty == 1


def test_rejects_when_budget_used_up():
    d = risk.size(CFG, flat_acct(open_notional=950, open_symbols=frozenset({"MSFT"})), SETUP)
    assert not d.approved


def test_no_reentry_same_day():
    d = risk.size(CFG, flat_acct(symbols_traded_today=frozenset({"AAPL"})), SETUP)
    assert not d.approved and "already traded" in d.reason


@pytest.mark.parametrize("acct,now,why", [
    (flat_acct(), at(9, 40), "outside entry window"),
    (flat_acct(), at(12, 0), "outside entry window"),
    (flat_acct(day_pnl=-31), at(10, 0), "daily loss"),
    (flat_acct(trades_today=3), at(10, 0), "trades per day"),
    (flat_acct(open_symbols=frozenset({"A", "B"})), at(10, 0), "open positions"),
    (flat_acct(daytrade_count=3), at(10, 0), "pattern-day-trader"),
    (flat_acct(trading_blocked=True), at(10, 0), "blocked"),
])
def test_account_gate_vetoes(acct, now, why):
    d = risk.can_open_new_trades(CFG, acct, now)
    assert not d.approved and why in d.reason


def test_account_gate_allows_normal_morning():
    assert risk.can_open_new_trades(CFG, flat_acct(), at(10, 0)).approved


# --- Orchestration with a fake broker -------------------------------------------

class FakeBroker:
    def __init__(self, acct, bars, is_open=True):
        self.acct, self.bars, self.is_open = acct, bars, is_open
        self.orders, self.flattened = [], 0

    def market_open(self):
        return self.is_open

    def account_state(self, now):
        return self.acct

    def intraday_bars(self, symbols, now):
        return self.bars

    def daily_stats(self, symbols, now):
        return {s: (99.0, 2_000_000) for s in self.bars}

    def buy_bracket(self, setup, qty, now):
        self.orders.append((setup.symbol, qty, setup.stop, setup.target))
        return "id"

    def flatten_all(self):
        self.flattened += 1
        return 0


def fake(acct=None, **kw):
    bars = {"SPY": make_bars([500, 501, 502, 503]), "AAPL": breakout_bars(), "MSFT": breakout_bars()}
    return FakeBroker(acct or flat_acct(), bars, **kw)


def test_run_places_bracket_orders_within_limits():
    b = fake()
    run(Settings(), b, at(9, 55))
    assert [o[0] for o in b.orders] == ["AAPL", "MSFT"]  # max 2 open positions
    assert all(o[1] >= 1 for o in b.orders)


def test_run_dry_run_sends_nothing(monkeypatch):
    monkeypatch.setenv("TRADING_ENABLED", "false")
    b = fake()
    run(Settings(), b, at(9, 55))
    assert b.orders == []


def test_run_flattens_near_close():
    b = fake()
    run(Settings(), b, at(15, 50))
    assert b.flattened == 1 and b.orders == []


def test_run_stands_aside_in_weak_market():
    b = fake()
    b.bars["SPY"] = make_bars([503, 502, 501, 500])
    run(Settings(), b, at(9, 55))
    assert b.orders == []


def test_run_idle_when_market_closed():
    b = fake(is_open=False)
    run(Settings(), b, at(9, 55))
    assert b.orders == [] and b.flattened == 0
