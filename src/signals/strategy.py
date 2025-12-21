"""SMA crossover trading strategy."""
from datetime import datetime, time
from decimal import Decimal
from typing import List, Optional

from src.app.config import Config
from src.app.models import Bar, Signal, OrderSide


def is_market_hours(dt: datetime, config: Config) -> bool:
    """
    Check if given datetime is within market hours.

    Args:
        dt: Datetime to check
        config: Configuration with market hours

    Returns:
        True if within market hours
    """
    market_open = time(
        hour=config.market_open_hour,
        minute=config.market_open_minute
    )
    market_close = time(
        hour=config.market_close_hour,
        minute=config.market_close_minute
    )

    current_time = dt.time()

    # Check if weekday (0=Monday, 6=Sunday)
    if dt.weekday() >= 5:  # Saturday or Sunday
        return False

    return market_open <= current_time <= market_close


def calculate_sma(bars: List[Bar], period: int) -> Optional[Decimal]:
    """
    Calculate Simple Moving Average.

    Args:
        bars: List of bars (must be sorted oldest to newest)
        period: Number of periods for SMA

    Returns:
        SMA value or None if insufficient data
    """
    if len(bars) < period:
        return None

    # Take the last 'period' bars
    recent_bars = bars[-period:]
    total = sum(bar.close for bar in recent_bars)
    return total / period


class SMAStrategy:
    """Simple Moving Average crossover strategy."""

    def __init__(self, config: Config):
        """
        Initialize SMA strategy.

        Args:
            config: Configuration with SMA periods
        """
        self.config = config
        self.fast_period = config.sma_fast_period
        self.slow_period = config.sma_slow_period
        self.last_signal = {}  # Track last signal per symbol to avoid duplicates

    def generate_signals(
        self,
        symbol: str,
        bars: List[Bar],
        has_position: bool
    ) -> Optional[Signal]:
        """
        Generate trading signal based on SMA crossover.

        Strategy:
        - BUY when fast SMA crosses above slow SMA (and no position)
        - SELL when fast SMA crosses below slow SMA (and has position)

        Args:
            symbol: Trading symbol
            bars: Historical bars (sorted oldest to newest)
            has_position: Whether we currently have a position

        Returns:
            Signal or None
        """
        # Check if we have enough data
        if len(bars) < self.slow_period + 1:
            return None

        # Check market hours
        latest_bar = bars[-1]
        if not is_market_hours(latest_bar.timestamp, self.config):
            return None

        # Calculate SMAs for current and previous bar
        current_bars = bars
        previous_bars = bars[:-1]

        current_fast = calculate_sma(current_bars, self.fast_period)
        current_slow = calculate_sma(current_bars, self.slow_period)
        previous_fast = calculate_sma(previous_bars, self.fast_period)
        previous_slow = calculate_sma(previous_bars, self.slow_period)

        if None in (current_fast, current_slow, previous_fast, previous_slow):
            return None

        # Check for crossover
        # BUY signal: fast was below slow, now above (golden cross)
        if not has_position:
            if previous_fast <= previous_slow and current_fast > current_slow:
                signal = Signal(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    timestamp=latest_bar.timestamp,
                    reason=f"SMA golden cross: fast={current_fast:.2f} > slow={current_slow:.2f}",
                    price=latest_bar.close
                )
                self.last_signal[symbol] = signal
                return signal

        # SELL signal: fast was above slow, now below (death cross)
        if has_position:
            if previous_fast >= previous_slow and current_fast < current_slow:
                signal = Signal(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    timestamp=latest_bar.timestamp,
                    reason=f"SMA death cross: fast={current_fast:.2f} < slow={current_slow:.2f}",
                    price=latest_bar.close
                )
                self.last_signal[symbol] = signal
                return signal

        return None
