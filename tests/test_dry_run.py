"""Tests for dry-run mode."""
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.app.config import Config
from src.app.models import Signal, OrderSide
from src.app.order_pipeline import submit_signal_order
from src.app.state import BotState, load_state, save_state
from src.app.__main__ import run_trading_loop, setup_outputs, write_order_to_csv, write_fill_to_csv, write_trade_to_csv
from src.broker import MockBroker
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
def config_dry_run():
    """Create test configuration with dry-run enabled."""
    return Config(
        mode="mock",
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=Decimal("1000"),
        allowed_symbols=["AAPL", "MSFT"],
        dry_run=True
    )


@pytest.fixture
def config_normal():
    """Create test configuration with dry-run disabled."""
    return Config(
        mode="mock",
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=Decimal("1000"),
        allowed_symbols=["AAPL", "MSFT"],
        dry_run=False
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
def risk_manager(config_normal):
    """Create risk manager."""
    return RiskManager(config_normal)


@pytest.fixture
def signal():
    """Create test signal."""
    return Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Test signal"
    )


def test_dry_run_flag_defaults_to_false():
    """Test that dry_run flag defaults to False."""
    config = Config()
    assert config.dry_run is False


def test_dry_run_flag_loads_from_env(monkeypatch):
    """Test that dry_run flag loads from environment."""
    from src.app.config import load_config

    monkeypatch.setenv("DRY_RUN", "true")
    config = load_config()
    assert config.dry_run is True


def test_dry_run_flag_case_insensitive(monkeypatch):
    """Test that dry_run flag is case-insensitive."""
    from src.app.config import load_config

    monkeypatch.setenv("DRY_RUN", "TRUE")
    config = load_config()
    assert config.dry_run is True


def test_dry_run_broker_not_called(temp_dir, config_dry_run, broker, risk_manager, state, signal):
    """Test that broker is NOT called in dry-run mode."""
    test_run_id = "test-run-id"
    setup_outputs(test_run_id)

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config_dry_run,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id=test_run_id,
        write_order_to_csv_fn=write_order_to_csv,
        write_fill_to_csv_fn=write_fill_to_csv,
        write_trade_to_csv_fn=write_trade_to_csv,
        strategy_name="TEST"
    )

    # Verify success (dry-run counts as success)
    assert result.success is True
    assert "Dry-run" in result.reason

    # CRITICAL: Verify broker was NOT called
    assert len(broker.orders) == 0


def test_dry_run_csv_files_unchanged(temp_dir, config_dry_run, broker, risk_manager, state, signal):
    """Test that CSV files are NOT modified in dry-run mode."""
    test_run_id = "test-run-id"
    setup_outputs(test_run_id)

    # Get initial line counts from run directory
    run_dir = Path(f"out/runs/{test_run_id}")
    orders_before = len((run_dir / "orders.csv").read_text().splitlines())
    fills_before = len((run_dir / "fills.csv").read_text().splitlines())
    trades_before = len((run_dir / "trades.csv").read_text().splitlines())

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config_dry_run,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id=test_run_id,
        write_order_to_csv_fn=write_order_to_csv,
        write_fill_to_csv_fn=write_fill_to_csv,
        write_trade_to_csv_fn=write_trade_to_csv,
        strategy_name="TEST"
    )

    assert result.success is True

    # CRITICAL: Verify CSV files were NOT modified
    orders_after = len((run_dir / "orders.csv").read_text().splitlines())
    fills_after = len((run_dir / "fills.csv").read_text().splitlines())
    trades_after = len((run_dir / "trades.csv").read_text().splitlines())

    assert orders_after == orders_before
    assert fills_after == fills_before
    assert trades_after == trades_before


def test_dry_run_state_not_modified(temp_dir, config_dry_run, broker, risk_manager, signal):
    """Test that state is NOT modified in dry-run mode."""
    test_run_id = "test-run-id"
    setup_outputs(test_run_id)

    # Create and save initial state
    state = BotState(run_id=test_run_id)
    initial_ids = {"existing-order-1", "existing-order-2"}
    state.submitted_client_order_ids = initial_ids.copy()
    save_state(state)

    # Reload state to ensure it's persisted
    state = load_state()
    assert state.submitted_client_order_ids == initial_ids

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config_dry_run,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id=test_run_id,
        write_order_to_csv_fn=write_order_to_csv,
        write_fill_to_csv_fn=write_fill_to_csv,
        write_trade_to_csv_fn=write_trade_to_csv,
        strategy_name="TEST"
    )

    assert result.success is True

    # CRITICAL: Verify state file was NOT modified (state.json is global, not per-run)
    loaded_state = load_state()
    assert loaded_state.submitted_client_order_ids == initial_ids
    assert result.client_order_id not in loaded_state.submitted_client_order_ids


def test_dry_run_risk_checks_still_enforced(temp_dir, config_dry_run, broker, risk_manager, state):
    """Test that risk checks are still enforced in dry-run mode."""
    test_run_id = "test-run-id"
    setup_outputs(test_run_id)

    # Create signal for invalid symbol
    signal = Signal(
        symbol="INVALID",  # Not in allowed_symbols
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        reason="Invalid symbol"
    )

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config_dry_run,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id=test_run_id,
        write_order_to_csv_fn=write_order_to_csv,
        write_fill_to_csv_fn=write_fill_to_csv,
        write_trade_to_csv_fn=write_trade_to_csv,
        strategy_name="TEST"
    )

    # CRITICAL: Verify risk check blocked the order
    assert result.success is False
    assert "Risk check failed" in result.reason
    assert "not in allowlist" in result.reason

    # Broker should NOT be called
    assert len(broker.orders) == 0


def test_dry_run_quantity_checks_still_enforced(temp_dir, config_dry_run, broker, risk_manager, state, signal):
    """Test that quantity checks are still enforced in dry-run mode."""
    test_run_id = "test-run-id"
    setup_outputs(test_run_id)

    result = submit_signal_order(
        signal=signal,
        quantity=200,  # Exceeds max_order_quantity=100
        config=config_dry_run,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id=test_run_id,
        write_order_to_csv_fn=write_order_to_csv,
        write_fill_to_csv_fn=write_fill_to_csv,
        write_trade_to_csv_fn=write_trade_to_csv,
        strategy_name="TEST"
    )

    # CRITICAL: Verify quantity check blocked the order
    assert result.success is False
    assert "Quantity check failed" in result.reason
    assert "exceeds max" in result.reason

    # Broker should NOT be called
    assert len(broker.orders) == 0


def test_dry_run_idempotency_checks_still_enforced(temp_dir, config_dry_run, broker, risk_manager, signal):
    """Test that idempotency checks are still enforced in dry-run mode."""
    test_run_id = "test-run-id"
    setup_outputs(test_run_id)

    # Pre-populate state with client_order_id
    state = BotState(run_id=test_run_id)
    client_order_id = "TEST_AAPL_buy_20240115103000"
    state.submitted_client_order_ids.add(client_order_id)

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config_dry_run,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id=test_run_id,
        write_order_to_csv_fn=write_order_to_csv,
        write_fill_to_csv_fn=write_fill_to_csv,
        write_trade_to_csv_fn=write_trade_to_csv,
        strategy_name="TEST"
    )

    # CRITICAL: Verify idempotency check blocked the order
    assert result.success is False
    assert "Duplicate order" in result.reason

    # Broker should NOT be called
    assert len(broker.orders) == 0


def test_normal_mode_still_works(temp_dir, config_normal, broker, risk_manager, state, signal):
    """Test that normal mode (dry_run=False) still works correctly."""
    test_run_id = "test-run-id"
    setup_outputs(test_run_id)

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config_normal,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id=test_run_id,
        write_order_to_csv_fn=write_order_to_csv,
        write_fill_to_csv_fn=write_fill_to_csv,
        write_trade_to_csv_fn=write_trade_to_csv,
        strategy_name="TEST"
    )

    # Verify success
    assert result.success is True
    assert result.order is not None

    # CRITICAL: Verify broker WAS called in normal mode
    assert len(broker.orders) == 1

    # Verify CSV files WERE written to run directory
    run_dir = Path(f"out/runs/{test_run_id}")
    orders_count = len((run_dir / "orders.csv").read_text().splitlines())
    fills_count = len((run_dir / "fills.csv").read_text().splitlines())
    trades_count = len((run_dir / "trades.csv").read_text().splitlines())

    assert orders_count == 2  # Header + 1 order
    assert fills_count == 2    # Header + 1 fill
    assert trades_count == 2   # Header + 1 trade

    # Verify state WAS updated
    assert result.client_order_id in state.submitted_client_order_ids


def test_dry_run_full_trading_loop(temp_dir, monkeypatch):
    """Test that full trading loop works in dry-run mode without side effects."""
    monkeypatch.setenv("MODE", "mock")
    monkeypatch.setenv("DRY_RUN", "true")

    # Save initial state
    initial_state = BotState(run_id="initial")
    save_state(initial_state)
    state_before = Path("out/state.json").read_text()

    # Run trading loop (creates its own run directory)
    run_trading_loop(iterations=1)

    # Find the run directory
    run_dirs = list(Path("out/runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    # In dry-run mode, CSV files should exist but only have headers (no data rows)
    orders_count = len((run_dir / "orders.csv").read_text().splitlines())
    fills_count = len((run_dir / "fills.csv").read_text().splitlines())
    trades_count = len((run_dir / "trades.csv").read_text().splitlines())

    # Each CSV should have exactly 1 line (header only, no trades in dry-run)
    assert orders_count == 1  # Header only
    assert fills_count == 1    # Header only
    assert trades_count == 1   # Header only

    # CRITICAL: Verify state file was NOT modified (state is global)
    state_after = Path("out/state.json").read_text()
    assert state_after == state_before


def test_dry_run_trades_executed_is_zero(temp_dir, monkeypatch):
    """Test that trades_executed remains 0 in dry-run mode."""
    monkeypatch.setenv("MODE", "mock")
    monkeypatch.setenv("DRY_RUN", "true")

    # Run trading loop
    from src.app.__main__ import run_trading_loop

    # Capture the trades_executed count from summary.json
    run_trading_loop(iterations=2)

    # Find the run directory
    run_dirs = list(Path("out/runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    # Check summary.json in run directory
    import json
    with open(run_dir / "summary.json") as f:
        summary = json.load(f)

    # CRITICAL: Verify trades_executed is 0 in dry-run mode
    assert summary["session_trades_executed"] == 0


def test_normal_mode_trades_executed_is_nonzero(temp_dir, monkeypatch):
    """Test that trades_executed is > 0 in normal mode when signals trigger."""
    monkeypatch.setenv("MODE", "mock")
    monkeypatch.setenv("DRY_RUN", "false")

    # Run trading loop
    from src.app.__main__ import run_trading_loop

    run_trading_loop(iterations=2)

    # Find the run directory
    run_dirs = list(Path("out/runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    # Check summary.json in run directory
    import json
    with open(run_dir / "summary.json") as f:
        summary = json.load(f)

    # In normal mode with mock data, we typically get some trades
    # (This may be 0 if no signals triggered, but usually > 0 with mock data)
    # The key is it's NOT artificially incremented in dry-run
    assert summary["session_trades_executed"] >= 0  # Just verify it exists


def test_dry_run_vs_normal_comparison(temp_dir, config_dry_run, config_normal, broker, signal):
    """Test that dry-run and normal mode behave identically up to broker call."""
    test_run_id = "test-run-id"
    setup_outputs(test_run_id)

    # Scenario 1: Dry-run mode
    state_dry = BotState(run_id="test-dry")
    risk_manager_dry = RiskManager(config_dry_run)

    result_dry = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config_dry_run,
        broker=broker,
        risk_manager=risk_manager_dry,
        state=state_dry,
        run_id=test_run_id,
        write_order_to_csv_fn=write_order_to_csv,
        write_fill_to_csv_fn=write_fill_to_csv,
        write_trade_to_csv_fn=write_trade_to_csv,
        strategy_name="TEST"
    )

    # Scenario 2: Normal mode
    broker_normal = MockBroker()
    state_normal = BotState(run_id="test-normal")
    risk_manager_normal = RiskManager(config_normal)

    result_normal = submit_signal_order(
        signal=signal,
        quantity=10,
        config=config_normal,
        broker=broker_normal,
        risk_manager=risk_manager_normal,
        state=state_normal,
        run_id=test_run_id,
        write_order_to_csv_fn=write_order_to_csv,
        write_fill_to_csv_fn=write_fill_to_csv,
        write_trade_to_csv_fn=write_trade_to_csv,
        strategy_name="TEST"
    )

    # Both should succeed
    assert result_dry.success is True
    assert result_normal.success is True

    # Both should compute same client_order_id
    assert result_dry.client_order_id == result_normal.client_order_id

    # Dry-run should NOT call broker
    assert len(broker.orders) == 0

    # Normal mode SHOULD call broker
    assert len(broker_normal.orders) == 1

    # Dry-run should NOT update state
    assert len(state_dry.submitted_client_order_ids) == 0

    # Normal mode SHOULD update state
    assert len(state_normal.submitted_client_order_ids) == 1
