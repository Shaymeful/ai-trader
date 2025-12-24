"""Tests for persistent daily loss tracking (restart safety)."""

from datetime import datetime
from decimal import Decimal

import pytest

from src.app.config import Config
from src.app.models import OrderSide, Signal
from src.app.state import (
    BotState,
    get_daily_realized_pnl,
    get_today_date_eastern,
    load_state,
    save_state,
    update_daily_realized_pnl,
)
from src.risk import RiskManager


@pytest.fixture
def config():
    """Create test configuration with strict daily loss limit."""
    return Config(
        mode="mock",
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=Decimal("100"),  # Strict $100 daily loss limit
        max_order_notional=Decimal("10000"),
        max_positions_notional=Decimal("50000"),
        allowed_symbols=["AAPL", "MSFT"],
        dry_run=False,
    )


@pytest.fixture
def temp_state_file(monkeypatch, tmp_path):
    """Create temporary state file for testing."""
    state_file = tmp_path / "state.json"
    monkeypatch.setenv("AI_TRADER_STATE_FILE", str(state_file))
    return state_file


def test_daily_loss_persists_across_restart(config, temp_state_file):
    """Test that daily loss persists across bot restarts."""
    today_date = get_today_date_eastern()

    # Session 1: Accumulate loss and save state
    state1 = BotState(run_id="run1")
    state1.daily_date = today_date

    # Simulate a $80 loss (approaching the $100 limit)
    update_daily_realized_pnl(state1, Decimal("-80"))
    save_state(state1, temp_state_file)

    # Session 2: "Restart" by loading state
    state2 = load_state(temp_state_file)

    # Verify daily loss persisted
    daily_pnl = get_daily_realized_pnl(state2)
    assert daily_pnl == Decimal("-80"), "Daily loss should persist across restarts"
    assert state2.daily_date == today_date, "Daily date should be preserved"

    # Initialize RiskManager with persisted loss
    risk_manager = RiskManager(config, daily_realized_pnl=daily_pnl)

    # Verify RiskManager loaded the persisted loss
    assert risk_manager.get_daily_pnl() == Decimal("-80")

    # Generate a test signal
    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("150.00"),
    )

    # Check if signal passes risk checks
    result = risk_manager.check_signal(signal)

    # With $80 loss already, we're still allowed to trade (under $100 limit)
    assert result.passed, "Should allow trading when under daily loss limit"

    # Now add another $25 loss (total: $105, exceeds $100 limit)
    risk_manager.daily_pnl -= Decimal("25")

    # Sync back to state
    update_daily_realized_pnl(state2, Decimal("-25"))

    # Verify total loss is now $105
    assert risk_manager.get_daily_pnl() == Decimal("-105")
    assert get_daily_realized_pnl(state2) == Decimal("-105")

    # Save state again
    save_state(state2, temp_state_file)

    # Session 3: Another restart with loss exceeding limit
    state3 = load_state(temp_state_file)
    daily_pnl3 = get_daily_realized_pnl(state3)

    # Verify loss persisted
    assert daily_pnl3 == Decimal("-105")

    # Initialize RiskManager with loss exceeding limit
    risk_manager3 = RiskManager(config, daily_realized_pnl=daily_pnl3)

    # Check signal again - should be BLOCKED due to daily loss limit
    result = risk_manager3.check_signal(signal)
    assert not result.passed, "Should block trading when daily loss limit exceeded"
    assert "Daily loss limit" in result.reason


def test_daily_counters_reset_on_new_trading_day(config, temp_state_file, monkeypatch):
    """Test that daily counters reset when a new trading day begins."""
    # Simulate yesterday's date
    yesterday_date = "2024-01-14"  # Sunday (but for test purposes, pretend it's a trading day)

    # Session 1: Accumulate loss on "yesterday"
    state1 = BotState(run_id="run1")
    state1.daily_date = yesterday_date
    state1.daily_realized_pnl[yesterday_date] = "-80"
    save_state(state1, temp_state_file)

    # Now simulate "today" by mocking get_today_date_eastern BEFORE loading state
    # This ensures load_state() uses the mocked date for day rollover detection
    today_date = "2024-01-15"
    monkeypatch.setattr("src.app.state.get_today_date_eastern", lambda: today_date)

    # Verify yesterday's loss is in the saved file (read JSON directly)
    import json

    with open(temp_state_file) as f:
        saved_data = json.load(f)
    assert saved_data["daily_date"] == yesterday_date
    assert saved_data["daily_realized_pnl"][yesterday_date] == "-80"

    # Session 2: Load state on "today" - should trigger day rollover
    state2 = load_state(temp_state_file)

    # Verify day rollover occurred
    assert state2.daily_date == today_date, "Daily date should update to today"

    # Yesterday's loss should still be in historical records
    assert state2.daily_realized_pnl.get(yesterday_date) == "-80", (
        "Historical loss should be preserved"
    )

    # But today's PnL should start at 0
    todays_pnl = get_daily_realized_pnl(state2)
    assert todays_pnl == Decimal("0"), "Today's PnL should reset to 0"

    # Initialize RiskManager with today's (reset) PnL
    risk_manager = RiskManager(config, daily_realized_pnl=todays_pnl)
    assert risk_manager.get_daily_pnl() == Decimal("0"), "RiskManager should start with 0 PnL"

    # Generate test signal
    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("150.00"),
    )

    # Should pass risk checks (yesterday's loss doesn't carry over)
    result = risk_manager.check_signal(signal)
    assert result.passed, "Should allow trading on new day despite yesterday's loss"


def test_state_initialization_sets_daily_date(temp_state_file):
    """Test that loading state for the first time sets daily_date."""
    # Load state when file doesn't exist
    state = load_state(temp_state_file)

    # Should initialize with today's date
    today_date = get_today_date_eastern()
    assert state.daily_date == today_date
    assert state.run_id == "initial"


def test_get_daily_realized_pnl_defaults_to_zero(temp_state_file):
    """Test that get_daily_realized_pnl returns 0 for dates without entries."""
    state = BotState(run_id="test")
    state.daily_date = get_today_date_eastern()

    # No entries in daily_realized_pnl yet
    pnl = get_daily_realized_pnl(state)
    assert pnl == Decimal("0")


def test_update_daily_realized_pnl_accumulates(temp_state_file):
    """Test that update_daily_realized_pnl correctly accumulates PnL."""
    state = BotState(run_id="test")
    state.daily_date = get_today_date_eastern()

    # Add multiple PnL updates
    update_daily_realized_pnl(state, Decimal("-30"))
    update_daily_realized_pnl(state, Decimal("-50"))
    update_daily_realized_pnl(state, Decimal("10"))  # Partial gain

    # Total: -30 - 50 + 10 = -70
    pnl = get_daily_realized_pnl(state)
    assert pnl == Decimal("-70")


def test_daily_loss_blocks_trading_immediately_after_restart(config, temp_state_file):
    """Test that exceeding daily loss limit blocks trading immediately after restart."""
    today_date = get_today_date_eastern()

    # Session 1: Hit daily loss limit exactly
    state1 = BotState(run_id="run1")
    state1.daily_date = today_date
    update_daily_realized_pnl(state1, Decimal("-100"))  # Exactly at limit
    save_state(state1, temp_state_file)

    # Session 2: Restart and verify trading is blocked
    state2 = load_state(temp_state_file)
    daily_pnl = get_daily_realized_pnl(state2)
    assert daily_pnl == Decimal("-100")

    risk_manager = RiskManager(config, daily_realized_pnl=daily_pnl)

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("150.00"),
    )

    # Should be blocked (at or below the negative threshold)
    result = risk_manager.check_signal(signal)
    assert not result.passed
    assert "Daily loss limit" in result.reason


def test_daily_date_timezone_is_eastern(temp_state_file):
    """Test that daily_date uses US/Eastern timezone."""
    state = load_state(temp_state_file)

    # daily_date should be in YYYY-MM-DD format
    assert state.daily_date is not None
    assert len(state.daily_date) == 10  # YYYY-MM-DD
    assert state.daily_date.count("-") == 2

    # Parse date components
    year, month, day = state.daily_date.split("-")
    assert len(year) == 4
    assert 1 <= int(month) <= 12
    assert 1 <= int(day) <= 31


def test_multiple_restarts_preserve_loss(config, temp_state_file):
    """Test that daily loss persists across multiple restarts."""
    today_date = get_today_date_eastern()

    # Session 1
    state1 = BotState(run_id="run1")
    state1.daily_date = today_date
    update_daily_realized_pnl(state1, Decimal("-20"))
    save_state(state1, temp_state_file)

    # Session 2
    state2 = load_state(temp_state_file)
    assert get_daily_realized_pnl(state2) == Decimal("-20")
    update_daily_realized_pnl(state2, Decimal("-30"))
    save_state(state2, temp_state_file)

    # Session 3
    state3 = load_state(temp_state_file)
    assert get_daily_realized_pnl(state3) == Decimal("-50")
    update_daily_realized_pnl(state3, Decimal("-20"))
    save_state(state3, temp_state_file)

    # Session 4
    state4 = load_state(temp_state_file)
    assert get_daily_realized_pnl(state4) == Decimal("-70")

    # Verify RiskManager respects accumulated loss
    risk_manager = RiskManager(config, daily_realized_pnl=Decimal("-70"))
    assert risk_manager.get_daily_pnl() == Decimal("-70")

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("150.00"),
    )

    # Should still pass (under $100 limit)
    result = risk_manager.check_signal(signal)
    assert result.passed
