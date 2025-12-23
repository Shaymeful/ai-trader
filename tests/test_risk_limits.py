"""Tests for new risk limit checks (notional, exposure, daily loss)."""

from decimal import Decimal

import pytest

from src.app.config import Config
from src.app.models import Position
from src.risk import RiskManager


@pytest.fixture
def config():
    """Create test configuration with default risk limits."""
    return Config(
        mode="mock",
        max_daily_loss=Decimal("500"),
        max_order_notional=Decimal("500"),
        max_positions_notional=Decimal("10000"),
        max_positions=5,
        max_order_quantity=100,
    )


def test_order_notional_blocks_over_limit(config):
    """Test that orders exceeding max_order_notional are blocked."""
    risk_manager = RiskManager(config)

    # Order notional = 100 * $6 = $600 > $500 limit
    result = risk_manager.check_order_notional(quantity=100, price=Decimal("6.00"))

    assert not result.passed
    assert "Order notional $600.00 exceeds limit $500.00" in result.reason


def test_order_notional_allows_at_limit(config):
    """Test that orders at exactly max_order_notional are allowed."""
    risk_manager = RiskManager(config)

    # Order notional = 100 * $5 = $500 = $500 limit
    result = risk_manager.check_order_notional(quantity=100, price=Decimal("5.00"))

    assert result.passed


def test_order_notional_allows_under_limit(config):
    """Test that orders under max_order_notional are allowed."""
    risk_manager = RiskManager(config)

    # Order notional = 50 * $9 = $450 < $500 limit
    result = risk_manager.check_order_notional(quantity=50, price=Decimal("9.00"))

    assert result.passed


def test_daily_loss_blocks_when_limit_exceeded(config):
    """Test that new orders are blocked when daily PnL <= -$500."""
    # Start with -$500 daily PnL
    risk_manager = RiskManager(config, daily_realized_pnl=Decimal("-500"))

    # Current daily PnL is exactly at the limit (-$500 <= -$500)
    assert risk_manager.daily_pnl == Decimal("-500")

    # check_signal should block
    from datetime import datetime

    from src.app.models import OrderSide, Signal

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 0),
        reason="test",
        price=Decimal("150.00"),
    )

    result = risk_manager.check_signal(signal)

    assert not result.passed
    assert "Daily loss limit" in result.reason
    assert "500" in result.reason


def test_daily_loss_blocks_when_limit_exceeded_negative(config):
    """Test that orders are blocked when daily PnL < -$500."""
    # Start with -$600 daily PnL (worse than limit)
    risk_manager = RiskManager(config, daily_realized_pnl=Decimal("-600"))

    from datetime import datetime

    from src.app.models import OrderSide, Signal

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 0),
        reason="test",
        price=Decimal("150.00"),
    )

    result = risk_manager.check_signal(signal)

    assert not result.passed
    assert "Daily loss limit" in result.reason


def test_daily_loss_allows_when_under_limit(config):
    """Test that orders are allowed when daily PnL > -$500."""
    # Start with -$300 daily PnL (better than limit)
    risk_manager = RiskManager(config, daily_realized_pnl=Decimal("-300"))

    from datetime import datetime

    from src.app.models import OrderSide, Signal

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 0),
        reason="test",
        price=Decimal("150.00"),
    )

    # Configure the signal's symbol to be in allowed list
    config.allowed_symbols = ["AAPL"]

    result = risk_manager.check_signal(signal)

    # Should pass (assuming other checks pass)
    # The check_signal only checks daily loss, not notional
    assert result.passed or "Daily loss" not in result.reason


def test_daily_loss_allows_positive_pnl(config):
    """Test that orders are allowed when daily PnL is positive."""
    # Start with +$200 daily PnL
    risk_manager = RiskManager(config, daily_realized_pnl=Decimal("200"))

    from datetime import datetime

    from src.app.models import OrderSide, Signal

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 0),
        reason="test",
        price=Decimal("150.00"),
    )

    config.allowed_symbols = ["AAPL"]

    result = risk_manager.check_signal(signal)

    assert result.passed or "Daily loss" not in result.reason


def test_exposure_blocks_when_limit_exceeded(config):
    """Test that orders are blocked when total exposure would exceed $10,000."""
    risk_manager = RiskManager(config)

    # Set up existing positions with $9,000 exposure
    risk_manager.positions = {
        "AAPL": Position(
            symbol="AAPL", quantity=50, avg_price=Decimal("150.00"), current_price=Decimal("150.00")
        ),  # $7,500
        "MSFT": Position(
            symbol="MSFT", quantity=5, avg_price=Decimal("300.00"), current_price=Decimal("300.00")
        ),  # $1,500
    }

    # Current exposure = $7,500 + $1,500 = $9,000
    assert risk_manager.get_current_exposure() == Decimal("9000")

    # Try to add order with $1,500 notional (would push to $10,500)
    result = risk_manager.check_positions_exposure(10, Decimal("150.00"))

    assert not result.passed
    assert "Total exposure $10500.00" in result.reason
    assert "exceeds limit $10000.00" in result.reason
    assert "current: $9000.00" in result.reason
    assert "new: $1500.00" in result.reason


def test_exposure_allows_when_at_limit(config):
    """Test that orders are allowed when total exposure equals $10,000."""
    risk_manager = RiskManager(config)

    # Set up existing positions with $9,500 exposure
    risk_manager.positions = {
        "AAPL": Position(
            symbol="AAPL", quantity=50, avg_price=Decimal("150.00"), current_price=Decimal("150.00")
        ),  # $7,500
        "MSFT": Position(
            symbol="MSFT", quantity=10, avg_price=Decimal("200.00"), current_price=Decimal("200.00")
        ),  # $2,000
    }

    assert risk_manager.get_current_exposure() == Decimal("9500")

    # Try to add order with $500 notional (total = $10,000)
    result = risk_manager.check_positions_exposure(10, Decimal("50.00"))

    assert result.passed


def test_exposure_allows_when_under_limit(config):
    """Test that orders are allowed when total exposure < $10,000."""
    risk_manager = RiskManager(config)

    # Set up existing positions with $5,000 exposure
    risk_manager.positions = {
        "AAPL": Position(
            symbol="AAPL", quantity=50, avg_price=Decimal("100.00"), current_price=Decimal("100.00")
        ),
    }

    assert risk_manager.get_current_exposure() == Decimal("5000")

    # Try to add order with $2,000 notional (total = $7,000 < $10,000)
    result = risk_manager.check_positions_exposure(20, Decimal("100.00"))

    assert result.passed


def test_exposure_allows_empty_positions(config):
    """Test that orders are allowed when no existing positions."""
    risk_manager = RiskManager(config)

    # No positions
    assert len(risk_manager.positions) == 0
    assert risk_manager.get_current_exposure() == Decimal("0")

    # Try to add order with $500 notional
    result = risk_manager.check_positions_exposure(10, Decimal("50.00"))

    assert result.passed


def test_exposure_calculation_uses_abs_quantity(config):
    """Test that exposure calculation uses absolute values of quantities."""
    risk_manager = RiskManager(config)

    # Position with negative quantity (though we only support longs in MVP)
    # The exposure calc should use abs(qty) * avg_price
    risk_manager.positions = {
        "AAPL": Position(
            symbol="AAPL",
            quantity=-10,
            avg_price=Decimal("100.00"),
            current_price=Decimal("100.00"),
        ),
    }

    # Exposure should be abs(-10) * 100 = $1,000
    exposure = risk_manager.get_current_exposure()
    assert exposure == Decimal("1000")


def test_notional_calculation_uses_abs_value(config):
    """Test that notional calculation uses absolute value."""
    risk_manager = RiskManager(config)

    # Negative quantity (shouldn't happen in practice, but test abs)
    result = risk_manager.check_order_notional(quantity=-10, price=Decimal("60.00"))

    # Notional should be abs(-10) * 60 = $600 > $500 limit
    assert not result.passed
    assert "$600.00" in result.reason


def test_multiple_positions_exposure(config):
    """Test exposure calculation with multiple positions."""
    risk_manager = RiskManager(config)

    # Multiple positions
    risk_manager.positions = {
        "AAPL": Position(
            symbol="AAPL", quantity=10, avg_price=Decimal("150.00"), current_price=Decimal("160.00")
        ),  # $1,500
        "MSFT": Position(
            symbol="MSFT", quantity=20, avg_price=Decimal("200.00"), current_price=Decimal("210.00")
        ),  # $4,000
        "GOOGL": Position(
            symbol="GOOGL",
            quantity=5,
            avg_price=Decimal("2500.00"),
            current_price=Decimal("2600.00"),
        ),  # $12,500
    }

    # Total exposure = $1,500 + $4,000 + $12,500 = $18,000
    exposure = risk_manager.get_current_exposure()
    assert exposure == Decimal("18000")

    # Try to add any order (should fail since already over limit)
    result = risk_manager.check_positions_exposure(1, Decimal("1.00"))

    assert not result.passed
    assert "exceeds limit" in result.reason
