"""SMA crossover trading strategy."""

from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.app.config import Config
from src.app.models import Bar, OrderSide, Signal


def get_exchange_time() -> datetime:
    """
    Get current time in US Eastern timezone (America/New_York).

    Returns:
        Current datetime in US Eastern timezone
    """
    eastern = ZoneInfo("America/New_York")
    return datetime.now(eastern)


def is_market_hours(config: Config, current_time: datetime | None = None) -> bool:
    """
    Check if current time is within market hours.

    Uses actual current time in US Eastern timezone, not bar timestamps.
    Respects weekends (no trading on Saturday/Sunday).

    Args:
        config: Configuration with market hours
        current_time: Optional datetime to check (defaults to current exchange time)

    Returns:
        True if within market hours on a weekday
    """
    if current_time is None:
        current_time = get_exchange_time()

    # Ensure we're working with timezone-aware datetime in Eastern time
    eastern = ZoneInfo("America/New_York")
    if current_time.tzinfo is None:
        # If naive, assume it's already Eastern time
        current_time = current_time.replace(tzinfo=eastern)
    else:
        # Convert to Eastern time if it's in a different timezone
        current_time = current_time.astimezone(eastern)

    # Check if weekday (0=Monday, 4=Friday, 5=Saturday, 6=Sunday)
    if current_time.weekday() >= 5:
        return False

    # Check time bounds
    market_open = time(hour=config.market_open_hour, minute=config.market_open_minute)
    market_close = time(hour=config.market_close_hour, minute=config.market_close_minute)

    current_time_only = current_time.time()
    return market_open <= current_time_only <= market_close


def calculate_sma(bars: list[Bar], period: int) -> Decimal | None:
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

    def generate_signals(self, symbol: str, bars: list[Bar], has_position: bool) -> Signal | None:
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

        # Check market hours using actual current time (not bar timestamp)
        if not is_market_hours(self.config):
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

        # Get latest bar for signal timestamp and price
        latest_bar = bars[-1]

        # Check for crossover
        # BUY signal: fast was below slow, now above (golden cross)
        if not has_position and previous_fast <= previous_slow and current_fast > current_slow:
            signal = Signal(
                symbol=symbol,
                side=OrderSide.BUY,
                timestamp=latest_bar.timestamp,
                reason=f"SMA golden cross: fast={current_fast:.2f} > slow={current_slow:.2f}",
                price=latest_bar.close,
            )
            self.last_signal[symbol] = signal
            return signal

        # SELL signal: fast was above slow, now below (death cross)
        if has_position and previous_fast >= previous_slow and current_fast < current_slow:
            signal = Signal(
                symbol=symbol,
                side=OrderSide.SELL,
                timestamp=latest_bar.timestamp,
                reason=f"SMA death cross: fast={current_fast:.2f} < slow={current_slow:.2f}",
                price=latest_bar.close,
            )
            self.last_signal[symbol] = signal
            return signal

        return None
