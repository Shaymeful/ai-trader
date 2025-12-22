"""Tests for risk management module."""

from datetime import datetime
from decimal import Decimal

import pytest

from src.app.config import Config
from src.app.models import OrderSide, Signal
from src.risk import RiskManager


@pytest.fixture
def config():
    """Create test configuration."""
    return Config(
        max_positions=3,
        max_order_quantity=50,
        max_daily_loss=Decimal("500"),
        allowed_symbols=["AAPL", "MSFT", "GOOGL"],
    )


@pytest.fixture
def risk_manager(config):
    """Create risk manager instance."""
    return RiskManager(config)


def test_signal_passes_basic_checks(risk_manager):
    """Test that valid signal passes all checks."""
    signal = Signal(
        symbol="AAPL", side=OrderSide.BUY, timestamp=datetime.now(), reason="Test signal"
    )

    result = risk_manager.check_signal(signal)
    assert result.passed is True


def test_symbol_not_in_allowlist(risk_manager):
    """Test that signal for non-allowed symbol is rejected."""
    signal = Signal(
        symbol="INVALID", side=OrderSide.BUY, timestamp=datetime.now(), reason="Test signal"
    )

    result = risk_manager.check_signal(signal)
    assert result.passed is False
    assert "not in allowlist" in result.reason


def test_max_positions_limit(risk_manager):
    """Test that max positions limit is enforced."""
    # Fill up to max positions
    for _i, symbol in enumerate(["AAPL", "MSFT", "GOOGL"]):
        risk_manager.update_position(symbol, 10, Decimal("100"))

    # Try to add one more
    signal = Signal(
        symbol="AAPL", side=OrderSide.BUY, timestamp=datetime.now(), reason="Test signal"
    )

    result = risk_manager.check_signal(signal)
    assert result.passed is False
    assert "Max positions" in result.reason


def test_daily_loss_limit(risk_manager):
    """Test that daily loss limit is enforced."""
    # Simulate a large loss
    risk_manager.daily_pnl = Decimal("-600")

    signal = Signal(
        symbol="AAPL", side=OrderSide.BUY, timestamp=datetime.now(), reason="Test signal"
    )

    result = risk_manager.check_signal(signal)
    assert result.passed is False
    assert "Daily loss limit" in result.reason


def test_order_quantity_too_large(risk_manager):
    """Test that excessive order quantity is rejected."""
    result = risk_manager.check_order_quantity(100)
    assert result.passed is False


def test_order_quantity_negative(risk_manager):
    """Test that negative quantity is rejected."""
    result = risk_manager.check_order_quantity(-10)
    assert result.passed is False


def test_order_quantity_valid(risk_manager):
    """Test that valid quantity passes."""
    result = risk_manager.check_order_quantity(30)
    assert result.passed is True


def test_position_update_new_position(risk_manager):
    """Test creating a new position."""
    risk_manager.update_position("AAPL", 10, Decimal("150"))

    assert "AAPL" in risk_manager.positions
    pos = risk_manager.positions["AAPL"]
    assert pos.quantity == 10
    assert pos.avg_price == Decimal("150")


def test_position_update_close_position(risk_manager):
    """Test closing a position updates PnL."""
    # Open position
    risk_manager.update_position("AAPL", 10, Decimal("100"))

    # Close position at profit
    risk_manager.update_position("AAPL", -10, Decimal("110"))

    assert "AAPL" not in risk_manager.positions
    assert risk_manager.daily_pnl == Decimal("100")  # 10 shares * $10 profit


def test_reset_daily_pnl(risk_manager):
    """Test resetting daily PnL."""
    risk_manager.daily_pnl = Decimal("100")
    risk_manager.reset_daily_pnl()
    assert risk_manager.daily_pnl == Decimal("0")
