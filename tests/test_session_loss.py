"""Tests for session kill switch safety feature."""

from datetime import datetime
from decimal import Decimal

import pytest

from src.app.config import Config
from src.app.models import OrderSide, Signal
from src.risk import RiskManager


@pytest.fixture
def config_with_session_limit():
    """Create test configuration with session loss limit enabled."""
    return Config(
        mode="mock",
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=Decimal("500"),
        max_session_loss=Decimal("100"),  # $100 session loss limit
        max_order_notional=Decimal("10000"),
        max_positions_notional=Decimal("50000"),
        allowed_symbols=["AAPL", "MSFT"],
        dry_run=False,
    )


@pytest.fixture
def config_without_session_limit():
    """Create test configuration with session loss limit disabled."""
    return Config(
        mode="mock",
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=Decimal("500"),
        max_session_loss=None,  # Disabled
        max_order_notional=Decimal("10000"),
        max_positions_notional=Decimal("50000"),
        allowed_symbols=["AAPL", "MSFT"],
        dry_run=False,
    )


def test_session_loss_disabled_by_default():
    """Test that session loss limit is disabled by default (None)."""
    config = Config(mode="mock")
    risk_manager = RiskManager(config)

    # Simulate large session loss
    risk_manager.session_pnl = Decimal("-1000")

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("150.00"),
    )

    # Should pass because session limit is disabled
    result = risk_manager.check_signal(signal)
    assert result.passed, "Should pass when session limit is disabled (None)"


def test_session_loss_blocks_when_limit_exceeded(config_with_session_limit, caplog):
    """Test that session kill switch blocks orders when limit is exceeded."""
    risk_manager = RiskManager(config_with_session_limit)

    # Simulate loss exceeding the limit
    risk_manager.session_pnl = Decimal("-105")  # Exceeds $100 limit

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("150.00"),
    )

    # Should be blocked
    result = risk_manager.check_signal(signal)
    assert not result.passed, "Should block when session loss limit exceeded"
    assert "Session loss limit" in result.reason
    assert "100" in result.reason  # Mentions the limit

    # Check that WARNING was logged
    assert "SESSION KILL SWITCH TRIGGERED" in caplog.text
    assert "Blocking all new orders" in caplog.text


def test_session_loss_allows_trading_under_limit(config_with_session_limit):
    """Test that trading is allowed when under session loss limit."""
    risk_manager = RiskManager(config_with_session_limit)

    # Simulate loss under the limit
    risk_manager.session_pnl = Decimal("-80")  # Under $100 limit

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("150.00"),
    )

    # Should pass
    result = risk_manager.check_signal(signal)
    assert result.passed, "Should allow trading when under session loss limit"


def test_session_loss_at_exact_threshold(config_with_session_limit):
    """Test behavior when session loss is exactly at the threshold."""
    risk_manager = RiskManager(config_with_session_limit)

    # Simulate loss exactly at the limit
    risk_manager.session_pnl = Decimal("-100")  # Exactly at $100 limit

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("150.00"),
    )

    # Should be blocked (using <= comparison)
    result = risk_manager.check_signal(signal)
    assert not result.passed, "Should block when session loss is exactly at limit"


def test_session_loss_accumulates_from_position_closes(config_with_session_limit):
    """Test that session PnL accumulates when positions are closed."""
    risk_manager = RiskManager(config_with_session_limit)

    # Open a position
    risk_manager.update_position("AAPL", 10, Decimal("150.00"))
    assert risk_manager.session_pnl == Decimal("0"), "Session PnL should be 0 initially"

    # Close position at a loss
    risk_manager.update_position("AAPL", -10, Decimal("140.00"))  # $10 loss per share = $100 total

    # Verify session PnL updated
    assert risk_manager.session_pnl == Decimal("-100"), "Session PnL should reflect position loss"

    # Try to place new order - should be blocked
    signal = Signal(
        symbol="MSFT",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("200.00"),
    )

    result = risk_manager.check_signal(signal)
    assert not result.passed, "Should block after session loss from closed position"


def test_session_loss_partial_position_close(config_with_session_limit):
    """Test that session PnL accumulates from partial position closes."""
    risk_manager = RiskManager(config_with_session_limit)

    # Open a position (20 shares @ $150)
    risk_manager.update_position("AAPL", 20, Decimal("150.00"))

    # Partially close position at a loss (sell 10 shares @ $140)
    risk_manager.update_position("AAPL", -10, Decimal("140.00"))  # $10 loss per share = $100 total

    # Verify session PnL updated
    assert risk_manager.session_pnl == Decimal("-100"), (
        "Session PnL should reflect partial close loss"
    )

    # Should be blocked
    signal = Signal(
        symbol="MSFT",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("200.00"),
    )

    result = risk_manager.check_signal(signal)
    assert not result.passed, "Should block after session loss from partial close"


def test_session_loss_not_persisted_across_restarts(config_with_session_limit):
    """Test that session loss does NOT persist across bot restarts."""
    # Session 1: Accumulate loss
    risk_manager1 = RiskManager(config_with_session_limit)
    risk_manager1.session_pnl = Decimal("-105")  # Exceeds limit

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("150.00"),
    )

    # Should be blocked in session 1
    result1 = risk_manager1.check_signal(signal)
    assert not result1.passed, "Should block in first session"

    # Session 2: "Restart" by creating new RiskManager
    # Note: In real code, daily_pnl would be loaded from state, but session_pnl would NOT
    risk_manager2 = RiskManager(config_with_session_limit, daily_realized_pnl=Decimal("-105"))

    # session_pnl should be 0 (not persisted)
    assert risk_manager2.session_pnl == Decimal("0"), "Session PnL should reset on restart"

    # Should pass in session 2 (session loss reset)
    result2 = risk_manager2.check_signal(signal)
    assert result2.passed, "Should allow trading after restart (session loss reset)"


def test_session_kill_switch_warning_logged_once(config_with_session_limit, caplog):
    """Test that kill switch warning is only logged once to avoid spam."""
    risk_manager = RiskManager(config_with_session_limit)
    risk_manager.session_pnl = Decimal("-105")

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("150.00"),
    )

    # First check - should log warning
    caplog.clear()
    result1 = risk_manager.check_signal(signal)
    assert not result1.passed
    warning_count_1 = caplog.text.count("SESSION KILL SWITCH TRIGGERED")
    assert warning_count_1 == 1, "Should log warning on first trip"

    # Second check - should NOT log warning again
    caplog.clear()
    result2 = risk_manager.check_signal(signal)
    assert not result2.passed
    warning_count_2 = caplog.text.count("SESSION KILL SWITCH TRIGGERED")
    assert warning_count_2 == 0, "Should not log warning again on subsequent checks"


def test_session_and_daily_loss_independent(config_with_session_limit):
    """Test that session loss and daily loss are tracked independently."""
    # Initialize with daily loss from state (persisted)
    risk_manager = RiskManager(config_with_session_limit, daily_realized_pnl=Decimal("-50"))

    # Verify initial state
    assert risk_manager.daily_pnl == Decimal("-50"), "Daily PnL should be loaded from state"
    assert risk_manager.session_pnl == Decimal("0"), "Session PnL should start at 0"

    # Close a position at a loss
    risk_manager.update_position("AAPL", 10, Decimal("150.00"))
    risk_manager.update_position("AAPL", -10, Decimal("140.00"))  # $100 loss

    # Both should be updated
    assert risk_manager.daily_pnl == Decimal("-150"), "Daily PnL should include new loss"
    assert risk_manager.session_pnl == Decimal("-100"), "Session PnL should include new loss"


def test_session_loss_works_in_mock_mode():
    """Test that session loss limit works in mock mode without Alpaca credentials."""
    config = Config(
        mode="mock",
        max_session_loss=Decimal("50"),
        allowed_symbols=["AAPL"],
    )

    risk_manager = RiskManager(config)
    risk_manager.session_pnl = Decimal("-60")

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("150.00"),
    )

    result = risk_manager.check_signal(signal)
    assert not result.passed, "Should work in mock mode"
    assert "Session loss limit" in result.reason
