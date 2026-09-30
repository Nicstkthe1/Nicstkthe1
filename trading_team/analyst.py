"""Analyst: finds opening-range-breakout momentum setups. Pure logic, no broker calls."""

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional, Sequence

from .config import Settings


@dataclass(frozen=True)
class Bar:
    t: datetime  # bar start, US/Eastern
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Setup:
    symbol: str
    entry: float
    stop: float
    target: float
    relative_volume: float
    score: float
    reason: str

    @property
    def risk_per_share(self) -> float:
        return self.entry - self.stop


def vwap(bars: Sequence[Bar]) -> float:
    vol = sum(b.volume for b in bars)
    if vol <= 0:
        return bars[-1].close
    return sum((b.high + b.low + b.close) / 3 * b.volume for b in bars) / vol


def opening_range(bars: Sequence[Bar], minutes: int) -> Optional[tuple]:
    """(high, low) of the bars inside the first `minutes` of the session."""
    start = time(9, 30)
    end_minute = 9 * 60 + 30 + minutes
    inside = [b for b in bars if start <= b.t.time() and b.t.hour * 60 + b.t.minute < end_minute]
    if not inside or len(inside) < max(1, minutes // 5):
        return None
    return max(b.high for b in inside), min(b.low for b in inside)


def relative_volume(bars: Sequence[Bar], avg_daily_volume: float, now: datetime) -> float:
    """Today's volume so far vs. what an average day would have traded by now."""
    if avg_daily_volume <= 0:
        return 0.0
    elapsed = max(5, (now.hour * 60 + now.minute) - (9 * 60 + 30))
    expected = avg_daily_volume * min(1.0, elapsed / 390)
    return sum(b.volume for b in bars) / expected


def market_is_healthy(spy_bars: Sequence[Bar]) -> bool:
    """Only buy breakouts when the broad market is trading above its VWAP."""
    return bool(spy_bars) and spy_bars[-1].close > vwap(spy_bars)


def find_setup(
    symbol: str,
    bars: Sequence[Bar],
    prev_close: float,
    avg_daily_volume: float,
    now: datetime,
    cfg: Settings,
) -> tuple[Optional[Setup], str]:
    """Return (setup, reason). setup is None when the symbol doesn't qualify."""
    if len(bars) < 4:
        return None, "not enough bars yet"
    rng = opening_range(bars, cfg.opening_range_minutes)
    if rng is None:
        return None, "opening range incomplete"
    or_high, or_low = rng
    last = bars[-1]
    price = last.close

    if price < cfg.min_price:
        return None, f"price {price:.2f} below ${cfg.min_price:.0f} minimum"
    if price <= or_high:
        return None, f"no breakout ({price:.2f} <= OR high {or_high:.2f})"
    if price > or_high * (1 + cfg.max_chase_pct / 100):
        return None, f"too extended ({(price / or_high - 1) * 100:.1f}% past OR high), won't chase"
    session_vwap = vwap(bars)
    if price <= session_vwap:
        return None, f"below VWAP {session_vwap:.2f}"
    if prev_close > 0 and price <= prev_close:
        return None, "red on the day"
    rvol = relative_volume(bars, avg_daily_volume, now)
    if rvol < cfg.min_relative_volume:
        return None, f"relative volume {rvol:.2f} < {cfg.min_relative_volume}"

    # Stop under the opening range; tighten to its midpoint if the range is too wide.
    stop = or_low
    if (price - stop) / price * 100 > cfg.max_stop_pct:
        stop = (or_high + or_low) / 2
    stop_pct = (price - stop) / price * 100
    if stop_pct > cfg.max_stop_pct:
        return None, f"stop too wide ({stop_pct:.1f}%)"
    if stop_pct < cfg.min_stop_pct:
        return None, f"stop too tight ({stop_pct:.2f}%)"

    target = price + cfg.reward_risk * (price - stop)
    breakout_strength = (price / or_high - 1) * 100
    score = rvol * (1 + breakout_strength)
    reason = (
        f"broke OR high {or_high:.2f}, above VWAP {session_vwap:.2f}, "
        f"rvol {rvol:.1f}x, stop {stop_pct:.1f}% away"
    )
    return (
        Setup(symbol, round(price, 2), round(stop, 2), round(target, 2), rvol, score, reason),
        reason,
    )
