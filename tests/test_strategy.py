"""Tests for trading strategy module."""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from src.app.config import Config
from src.app.models import Bar, OrderSide
from src.signals import SMAStrategy, is_market_hours
from src.signals.strategy import calculate_sma


@pytest.fixture
def config():
    """Create test configuration."""
    return Config(
        sma_fast_period=3,
        sma_slow_period=5,
        market_open_hour=9,
        market_open_minute=30,
        market_close_hour=16,
        market_close_minute=0
    )


@pytest.fixture
def strategy(config):
    """Create strategy instance."""
    return SMAStrategy(config)


def create_bars(symbol: str, prices: list, start_time: datetime = None) -> list:
    """Helper to create a list of bars with given close prices."""
    if start_time is None:
        start_time = datetime(2024, 1, 15, 10, 0)  # Monday at 10 AM

    bars = []
    for i, price in enumerate(prices):
        bar = Bar(
            symbol=symbol,
            timestamp=start_time + timedelta(minutes=i),
            open=Decimal(str(price)),
            high=Decimal(str(price + 1)),
            low=Decimal(str(price - 1)),
            close=Decimal(str(price)),
            volume=100000
        )
        bars.append(bar)
    return bars


def test_calculate_sma():
    """Test SMA calculation."""
    bars = create_bars("AAPL", [100, 102, 104, 106, 108])
    sma = calculate_sma(bars, 3)
    # Last 3: 104, 106, 108 -> average = 106
    assert sma == Decimal("106")


def test_calculate_sma_insufficient_data():
    """Test SMA returns None with insufficient data."""
    bars = create_bars("AAPL", [100, 102])
    sma = calculate_sma(bars, 3)
    assert sma is None


def test_is_market_hours_during_hours(config):
    """Test market hours check during trading hours."""
    dt = datetime(2024, 1, 15, 10, 0)  # Monday 10 AM
    assert is_market_hours(dt, config) is True


def test_is_market_hours_before_open(config):
    """Test market hours check before market open."""
    dt = datetime(2024, 1, 15, 9, 0)  # Monday 9 AM (before 9:30)
    assert is_market_hours(dt, config) is False


def test_is_market_hours_after_close(config):
    """Test market hours check after market close."""
    dt = datetime(2024, 1, 15, 17, 0)  # Monday 5 PM
    assert is_market_hours(dt, config) is False


def test_is_market_hours_weekend(config):
    """Test market hours check on weekend."""
    dt = datetime(2024, 1, 13, 10, 0)  # Saturday 10 AM
    assert is_market_hours(dt, config) is False


def test_golden_cross_generates_buy_signal(strategy):
    """Test that golden cross generates BUY signal."""
    # Prices that create golden cross: fast SMA crosses above slow SMA
    # Using fast=3, slow=5
    # Previous: fast < slow, Current: fast > slow
    prices = [90, 88, 86, 84, 82, 92, 100]
    bars = create_bars("AAPL", prices)

    signal = strategy.generate_signals("AAPL", bars, has_position=False)

    assert signal is not None
    assert signal.side == OrderSide.BUY
    assert "golden cross" in signal.reason.lower()


def test_death_cross_generates_sell_signal(strategy):
    """Test that death cross generates SELL signal."""
    # Prices that create death cross: fast SMA crosses below slow SMA
    # Previous: fast > slow, Current: fast < slow
    prices = [100, 102, 104, 106, 108, 98, 90]
    bars = create_bars("AAPL", prices)

    signal = strategy.generate_signals("AAPL", bars, has_position=True)

    assert signal is not None
    assert signal.side == OrderSide.SELL
    assert "death cross" in signal.reason.lower()


def test_no_signal_without_position_on_death_cross(strategy):
    """Test that no SELL signal without position."""
    prices = [110, 111, 112, 113, 114, 105, 100]
    bars = create_bars("AAPL", prices)

    signal = strategy.generate_signals("AAPL", bars, has_position=False)

    assert signal is None


def test_no_signal_with_position_on_golden_cross(strategy):
    """Test that no BUY signal when already have position."""
    prices = [100, 99, 98, 97, 96, 105, 110]
    bars = create_bars("AAPL", prices)

    signal = strategy.generate_signals("AAPL", bars, has_position=True)

    assert signal is None


def test_insufficient_bars_no_signal(strategy):
    """Test that insufficient data produces no signal."""
    bars = create_bars("AAPL", [100, 101, 102])  # Only 3 bars, need 6 (slow+1)

    signal = strategy.generate_signals("AAPL", bars, has_position=False)

    assert signal is None
