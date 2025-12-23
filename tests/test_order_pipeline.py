"""Tests for centralized order submission pipeline."""

import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.app.config import Config
from src.app.models import OrderSide, Signal
from src.app.order_pipeline import submit_signal_order
from src.app.state import BotState, load_state
from src.broker import MockBroker
from src.data.provider import MockDataProvider
from src.risk import RiskManager


@pytest.fixture
def temp_dir():
    """Create temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
        Path("out").mkdir(exist_ok=True)
        yield tmpdir
        os.chdir(original_cwd)


@pytest.fixture
def config():
    """Create test configuration."""
    return Config(
        mode="mock",
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=Decimal("1000"),
        max_order_notional=Decimal("10000"),
        max_positions_notional=Decimal("50000"),
        allowed_symbols=["AAPL", "MSFT"],
    )


@pytest.fixture
def state():
    """Create fresh bot state."""
    return BotState(run_id="test-run-id")


@pytest.fixture
def broker():
    """Create mock broker."""
    return MockBroker()


@pytest.fixture
def data_provider():
    """Create mock data provider."""
    return MockDataProvider()


@pytest.fixture
def risk_manager(config):
    """Create risk manager."""
    return RiskManager(config)


@pytest.fixture
def signal():
    """Create test signal."""
    from decimal import Decimal

    return Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal",
        price=Decimal("150.00"),
    )


@pytest.fixture
def write_fns():
    """Create mock CSV write functions."""
    return {"order": Mock(), "fill": Mock(), "trade": Mock()}


def test_successful_order_submission(
    temp_dir, config, broker, data_provider, risk_manager, state, signal, write_fns
):
    """Test successful order submission when all checks pass."""
    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run-id",
        write_order_to_csv_fn=write_fns["order"],
        write_fill_to_csv_fn=write_fns["fill"],
        write_trade_to_csv_fn=write_fns["trade"],
        data_provider=data_provider,
        strategy_name="TEST",
    )

    # Verify success
    assert result.success is True
    assert result.order is not None
    assert result.client_order_id is not None

    # Verify broker was called exactly once
    assert len(broker.orders) == 1
    order = list(broker.orders.values())[0]
    assert order.symbol == "AAPL"

    # Verify CSV write functions were called
    assert write_fns["order"].call_count == 1
    assert write_fns["fill"].call_count == 1
    assert write_fns["trade"].call_count == 1

    # Verify state was updated
    assert result.client_order_id in state.submitted_client_order_ids

    # Verify state was saved to file
    loaded_state = load_state()
    assert result.client_order_id in loaded_state.submitted_client_order_ids


def test_risk_check_signal_fails_broker_not_called(
    temp_dir, config, broker, data_provider, risk_manager, state, write_fns
):
    """Test that risk check failure prevents broker call."""
    # Create signal for symbol not in allowlist
    signal = Signal(
        symbol="INVALID",  # Not in allowed_symbols
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Invalid symbol",
    )

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run-id",
        write_order_to_csv_fn=write_fns["order"],
        write_fill_to_csv_fn=write_fns["fill"],
        write_trade_to_csv_fn=write_fns["trade"],
        data_provider=data_provider,
        strategy_name="TEST",
    )

    # Verify failure
    assert result.success is False
    assert "Risk check failed" in result.reason
    assert "not in allowlist" in result.reason

    # Verify broker was NOT called
    assert len(broker.orders) == 0

    # Verify CSV functions were NOT called
    assert write_fns["order"].call_count == 0
    assert write_fns["fill"].call_count == 0
    assert write_fns["trade"].call_count == 0

    # Verify state was NOT updated (no order submitted)
    assert result.client_order_id not in state.submitted_client_order_ids


def test_risk_check_max_positions_fails_broker_not_called(
    temp_dir, config, broker, data_provider, risk_manager, state, signal, write_fns
):
    """Test that max positions check prevents broker call."""
    # Fill up max positions
    for i in range(config.max_positions):
        risk_manager.update_position(f"SYM{i}", 10, Decimal("100.0"))

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run-id",
        write_order_to_csv_fn=write_fns["order"],
        write_fill_to_csv_fn=write_fns["fill"],
        write_trade_to_csv_fn=write_fns["trade"],
        data_provider=data_provider,
        strategy_name="TEST",
    )

    # Verify failure
    assert result.success is False
    assert "Max positions" in result.reason

    # Verify broker was NOT called
    assert len(broker.orders) == 0

    # Verify CSV functions were NOT called
    assert write_fns["order"].call_count == 0


def test_risk_check_daily_loss_fails_broker_not_called(
    temp_dir, config, broker, data_provider, risk_manager, state, signal, write_fns
):
    """Test that daily loss limit prevents broker call."""
    # Set daily PnL to exceed limit
    risk_manager.daily_pnl = -Decimal("1001")

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run-id",
        write_order_to_csv_fn=write_fns["order"],
        write_fill_to_csv_fn=write_fns["fill"],
        write_trade_to_csv_fn=write_fns["trade"],
        data_provider=data_provider,
        strategy_name="TEST",
    )

    # Verify failure
    assert result.success is False
    assert "Daily loss limit" in result.reason

    # Verify broker was NOT called
    assert len(broker.orders) == 0

    # Verify CSV functions were NOT called
    assert write_fns["order"].call_count == 0


def test_quantity_check_fails_broker_not_called(
    temp_dir, config, broker, data_provider, risk_manager, state, signal, write_fns
):
    """Test that quantity check prevents broker call."""
    # Request quantity that exceeds max
    result = submit_signal_order(
        signal=signal,
        quantity=200,  # Exceeds max_order_quantity=100
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run-id",
        write_order_to_csv_fn=write_fns["order"],
        write_fill_to_csv_fn=write_fns["fill"],
        write_trade_to_csv_fn=write_fns["trade"],
        data_provider=data_provider,
        strategy_name="TEST",
    )

    # Verify failure
    assert result.success is False
    assert "Quantity check failed" in result.reason
    assert "exceeds max" in result.reason

    # Verify broker was NOT called
    assert len(broker.orders) == 0

    # Verify CSV functions were NOT called
    assert write_fns["order"].call_count == 0


def test_idempotency_state_prevents_broker_call(
    temp_dir, config, broker, data_provider, risk_manager, state, signal, write_fns
):
    """Test that idempotency check (state) prevents duplicate broker call."""
    # Pre-populate state with client_order_id
    client_order_id = "TEST_AAPL_buy_20240115103000"
    state.submitted_client_order_ids.add(client_order_id)

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run-id",
        write_order_to_csv_fn=write_fns["order"],
        write_fill_to_csv_fn=write_fns["fill"],
        write_trade_to_csv_fn=write_fns["trade"],
        data_provider=data_provider,
        strategy_name="TEST",
    )

    # Verify failure
    assert result.success is False
    assert "Duplicate order" in result.reason
    assert "already in state" in result.reason

    # Verify broker was NOT called
    assert len(broker.orders) == 0

    # Verify CSV functions were NOT called
    assert write_fns["order"].call_count == 0


def test_idempotency_broker_prevents_duplicate(
    temp_dir, config, broker, data_provider, risk_manager, state, signal, write_fns
):
    """Test that idempotency check (broker) prevents duplicate submission."""
    # First submission
    result1 = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run-id",
        write_order_to_csv_fn=write_fns["order"],
        write_fill_to_csv_fn=write_fns["fill"],
        write_trade_to_csv_fn=write_fns["trade"],
        data_provider=data_provider,
        strategy_name="TEST",
    )

    assert result1.success is True
    assert len(broker.orders) == 1

    # Clear state but keep broker history
    state.submitted_client_order_ids.clear()

    # Second submission with same signal (should be caught by broker check)
    result2 = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run-id",
        write_order_to_csv_fn=write_fns["order"],
        write_fill_to_csv_fn=write_fns["fill"],
        write_trade_to_csv_fn=write_fns["trade"],
        data_provider=data_provider,
        strategy_name="TEST",
    )

    # Verify second submission was rejected
    assert result2.success is False
    assert "Duplicate order" in result2.reason
    assert "already in broker" in result2.reason

    # Verify broker still has only 1 order
    assert len(broker.orders) == 1

    # Verify state was updated to include the key (to prevent future checks)
    assert result1.client_order_id in state.submitted_client_order_ids


def test_all_checks_executed_in_order(temp_dir, config, data_provider, state, signal):
    """Test that checks are executed in the correct order."""
    # Track call order
    call_order = []

    # Create a mock broker that tracks calls
    broker = Mock()
    broker.order_exists = Mock(side_effect=lambda x: (call_order.append("order_exists"), False)[1])
    broker.submit_order = Mock(side_effect=lambda **kw: call_order.append("submit_order"))

    # Create a mock risk manager that tracks calls
    from src.risk.manager import RiskCheckResult

    risk_manager = Mock()

    def mock_check_signal(sig):
        call_order.append("check_signal")
        return RiskCheckResult(False, "Risk failed")

    def mock_check_quantity(qty):
        call_order.append("check_order_quantity")
        return RiskCheckResult(True, "")

    risk_manager.check_signal = Mock(side_effect=mock_check_signal)
    risk_manager.check_order_quantity = Mock(side_effect=mock_check_quantity)

    # Mock CSV write functions
    write_fns = {"order": Mock(), "fill": Mock(), "trade": Mock()}

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run-id",
        write_order_to_csv_fn=write_fns["order"],
        write_fill_to_csv_fn=write_fns["fill"],
        write_trade_to_csv_fn=write_fns["trade"],
        data_provider=data_provider,
        strategy_name="TEST",
    )

    # Verify failure at risk check
    assert result.success is False

    # Verify order of calls:
    # 1. broker.order_exists should be called (idempotency check)
    assert "order_exists" in call_order

    # 2. risk_manager.check_signal should be called
    assert "check_signal" in call_order

    # 3. risk_manager.check_order_quantity should NOT be called (failed earlier)
    assert "check_order_quantity" not in call_order

    # 4. broker.submit_order should NOT be called (risk check failed)
    assert "submit_order" not in call_order

    # Verify correct order
    assert call_order.index("order_exists") < call_order.index("check_signal")


def test_csv_files_only_written_on_success(
    temp_dir, config, broker, data_provider, risk_manager, state, signal
):
    """Test that CSV files are only written after successful submission."""
    # Create real CSV write functions that write to files
    from src.app.__main__ import (
        setup_outputs,
        write_fill_to_csv,
        write_order_to_csv,
        write_trade_to_csv,
    )

    test_run_id = "test-run-id"
    setup_outputs(test_run_id)

    # Get initial line counts from run directory
    run_dir = Path(f"out/runs/{test_run_id}")
    orders_before = len((run_dir / "orders.csv").read_text().splitlines())
    fills_before = len((run_dir / "fills.csv").read_text().splitlines())
    trades_before = len((run_dir / "trades.csv").read_text().splitlines())

    # Submit with invalid symbol (should fail risk check)
    signal_invalid = Signal(
        symbol="INVALID",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Invalid",
    )

    result_fail = submit_signal_order(
        signal=signal_invalid,
        quantity=10,
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id=test_run_id,
        write_order_to_csv_fn=write_order_to_csv,
        write_fill_to_csv_fn=write_fill_to_csv,
        write_trade_to_csv_fn=write_trade_to_csv,
        data_provider=data_provider,
        strategy_name="TEST",
    )

    assert result_fail.success is False

    # Verify CSV files were NOT modified
    orders_after_fail = len((run_dir / "orders.csv").read_text().splitlines())
    fills_after_fail = len((run_dir / "fills.csv").read_text().splitlines())
    trades_after_fail = len((run_dir / "trades.csv").read_text().splitlines())

    assert orders_after_fail == orders_before
    assert fills_after_fail == fills_before
    assert trades_after_fail == trades_before

    # Now submit valid order (should succeed)
    result_success = submit_signal_order(
        signal=signal,  # Valid signal
        quantity=10,
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id=test_run_id,
        write_order_to_csv_fn=write_order_to_csv,
        write_fill_to_csv_fn=write_fill_to_csv,
        write_trade_to_csv_fn=write_trade_to_csv,
        data_provider=data_provider,
        strategy_name="TEST",
    )

    assert result_success.success is True

    # Verify CSV files were NOW modified
    orders_after_success = len((run_dir / "orders.csv").read_text().splitlines())
    fills_after_success = len((run_dir / "fills.csv").read_text().splitlines())
    trades_after_success = len((run_dir / "trades.csv").read_text().splitlines())

    assert orders_after_success == orders_before + 1  # One new order
    assert fills_after_success == fills_before + 1  # One new fill
    assert trades_after_success == trades_before + 1  # One new trade


def test_deterministic_client_order_id(
    temp_dir, config, broker, data_provider, risk_manager, state, write_fns
):
    """Test that client_order_id is deterministic based on signal."""
    signal1 = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test",
        price=Decimal("150.00"),
    )

    signal2 = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),  # Same timestamp
        reason="Different reason",  # Reason doesn't affect ID
        price=Decimal("150.00"),
    )

    result1 = submit_signal_order(
        signal=signal1,
        quantity=10,
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run-id",
        write_order_to_csv_fn=write_fns["order"],
        write_fill_to_csv_fn=write_fns["fill"],
        write_trade_to_csv_fn=write_fns["trade"],
        data_provider=data_provider,
        strategy_name="TEST",
    )

    # Clear state for second attempt
    state.submitted_client_order_ids.clear()
    broker.orders.clear()
    broker.client_order_map.clear()

    result2 = submit_signal_order(
        signal=signal2,
        quantity=10,
        config=config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run-id",
        write_order_to_csv_fn=write_fns["order"],
        write_fill_to_csv_fn=write_fns["fill"],
        write_trade_to_csv_fn=write_fns["trade"],
        data_provider=data_provider,
        strategy_name="TEST",
    )

    # Both should succeed but have same client_order_id
    assert result1.success is True
    assert result2.success is True
    assert result1.client_order_id == result2.client_order_id
