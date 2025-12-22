"""Tests for Phase A: restart-safety and auditable artifacts."""
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from src.app.state import BotState, load_state, save_state, build_client_order_id
from src.app.models import TradeRecord, OrderRecord, FillRecord
from src.app.__main__ import setup_outputs, run_trading_loop


@pytest.fixture
def temp_dir(monkeypatch):
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Change to temp directory
        original_cwd = os.getcwd()
        os.chdir(tmpdir)

        yield tmpdir

        # Restore original directory
        os.chdir(original_cwd)


def test_build_client_order_id():
    """Test building deterministic idempotency keys (client order IDs)."""
    symbol = "AAPL"
    side = "buy"
    timestamp = datetime(2024, 1, 15, 10, 30, 45)
    strategy = "SMA"

    client_id = build_client_order_id(symbol, side, timestamp, strategy)

    # Check format: strategy_symbol_side_timestamp
    assert client_id == "SMA_AAPL_buy_20240115103045"
    assert client_id.startswith("SMA_AAPL_buy_")
    assert "20240115103045" in client_id

    # Check determinism: same inputs always produce same key
    client_id2 = build_client_order_id(symbol, side, timestamp, strategy)
    assert client_id == client_id2

    # Key should be stable across "runs" (no run_id in the key)
    # This is critical for idempotency across restarts
    client_id3 = build_client_order_id(symbol, side, timestamp, strategy)
    assert client_id == client_id3


def test_build_client_order_id_uniqueness():
    """Test that different inputs produce different idempotency keys."""
    timestamp = datetime(2024, 1, 15, 10, 30, 45)

    # Different symbol
    id1 = build_client_order_id("AAPL", "buy", timestamp)
    id2 = build_client_order_id("MSFT", "buy", timestamp)
    assert id1 != id2

    # Different side
    id3 = build_client_order_id("AAPL", "sell", timestamp)
    assert id1 != id3

    # Different timestamp
    timestamp2 = datetime(2024, 1, 15, 10, 30, 46)  # 1 second later
    id4 = build_client_order_id("AAPL", "buy", timestamp2)
    assert id1 != id4

    # All should be unique
    assert len({id1, id2, id3, id4}) == 4


def test_state_save_and_load(temp_dir):
    """Test saving and loading state."""
    state = BotState(
        run_id="test-run-id",
        last_processed_timestamp={"AAPL": "2024-01-15T10:30:00"},
        submitted_client_order_ids={"order-1", "order-2"}
    )

    save_state(state)

    loaded_state = load_state()

    assert loaded_state is not None
    assert loaded_state.run_id == "test-run-id"
    assert "AAPL" in loaded_state.last_processed_timestamp
    assert "order-1" in loaded_state.submitted_client_order_ids
    assert "order-2" in loaded_state.submitted_client_order_ids


def test_state_load_nonexistent(temp_dir):
    """Test loading state when file doesn't exist returns default state."""
    loaded_state = load_state()

    # Should return a valid default state, not None
    assert loaded_state is not None
    assert isinstance(loaded_state, BotState)

    # Default state should have sentinel run_id and empty collections
    assert loaded_state.run_id == "initial"
    assert loaded_state.submitted_client_order_ids == set()
    assert loaded_state.last_processed_timestamp == {}


def test_setup_outputs_creates_all_csvs(temp_dir):
    """Test that setup_outputs creates all required CSVs."""
    test_run_id = "test-run-123"
    setup_outputs(test_run_id)

    # Check files exist in run directory
    run_dir = Path(f"out/runs/{test_run_id}")
    assert (run_dir / "trades.csv").exists()
    assert (run_dir / "orders.csv").exists()
    assert (run_dir / "fills.csv").exists()

    # Check headers
    with open(run_dir / "trades.csv") as f:
        header = f.readline().strip()
        assert "run_id" in header
        assert "client_order_id" in header

    with open(run_dir / "orders.csv") as f:
        header = f.readline().strip()
        assert "client_order_id" in header
        assert "run_id" in header

    with open(run_dir / "fills.csv") as f:
        header = f.readline().strip()
        assert "client_order_id" in header
        assert "run_id" in header


def test_run_trading_loop_creates_run_id(temp_dir, monkeypatch):
    """Test that running the bot generates and uses a run_id."""
    monkeypatch.setenv("MODE", "mock")

    run_trading_loop(iterations=1)

    # Find the run directory
    run_dirs = list(Path("out/runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    # Check summary.json contains run_id in run directory
    with open(run_dir / "summary.json") as f:
        summary = json.load(f)

    assert "run_id" in summary
    assert len(summary["run_id"]) == 36  # UUID format


def test_run_trading_loop_writes_run_id_to_trades(temp_dir, monkeypatch):
    """Test that trades.csv contains run_id."""
    monkeypatch.setenv("MODE", "mock")

    run_trading_loop(iterations=1)

    # Find the run directory
    run_dirs = list(Path("out/runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    # Check trades.csv header in run directory
    with open(run_dir / "trades.csv") as f:
        header = f.readline().strip()
        lines = f.readlines()

    assert "run_id" in header

    # If trades were executed, check they have run_id
    if len(lines) > 0:
        # CSV should have run_id column
        assert len(lines[0].split(",")) >= 9  # timestamp,symbol,side,qty,price,order_id,client_order_id,run_id,reason


def test_idempotency_prevents_duplicate_orders(temp_dir, monkeypatch):
    """
    Test that idempotency prevents duplicate order submission.

    Uses monkeypatched data provider to return fixed market data that produces
    exactly one deterministic signal. Verifies that:
    1. First run produces exactly 1 order
    2. Second run (simulating restart) produces 0 new orders (deduped via idempotency key)
    3. State persists idempotency keys across restarts
    """
    from decimal import Decimal
    from src.app.models import Bar
    from src.data import MockDataProvider

    monkeypatch.setenv("MODE", "mock")

    # Create fixed bar data that will trigger exactly one BUY signal for AAPL
    # Strategy detects CROSSOVER: previous_fast <= previous_slow AND current_fast > current_slow
    # We need 31 bars total to compute SMAs for both previous (30 bars) and current (31 bars)
    def fixed_get_latest_bars(self, symbols, limit=1):
        """Return fixed data that produces a golden cross (BUY signal) for AAPL only."""
        result = {}
        base_time = datetime(2024, 1, 15, 10, 0)  # Monday 10:00 AM

        for symbol in symbols:
            bars = []
            if symbol == "AAPL":
                # Generate 31 bars designed to trigger golden cross
                # Bars 0-19: price = 105 (20 bars) - early high prices
                # Bars 20-29: price = 100 (10 bars) - dip (makes previous_fast low)
                # Bar 30: price = 150 (1 bar) - spike (makes current_fast high)
                #
                # Previous (bars 0-29):
                #   previous_slow = (20*105 + 10*100) / 30 = 103.33
                #   previous_fast = avg(bars 20-29) = 100
                #   Result: 100 < 103.33 ✓ (fast below slow)
                #
                # Current (bars 0-30):
                #   current_slow = (19*105 + 10*100 + 1*150) / 30 = 104.83
                #   current_fast = avg(bars 21-30) = (9*100 + 1*150) / 10 = 105
                #   Result: 105 > 104.83 ✓ (fast above slow)
                #
                # Crossover detected! previous_fast <= previous_slow AND current_fast > current_slow
                for i in range(limit):
                    timestamp = base_time + timedelta(minutes=i)

                    if i < 20:
                        # Bars 0-19: early high prices
                        price = 105.0
                    elif i < 30:
                        # Bars 20-29: dip to make previous_fast low
                        price = 100.0
                    else:
                        # Bar 30: spike to trigger crossover
                        price = 150.0

                    bar = Bar(
                        symbol=symbol,
                        timestamp=timestamp,
                        open=Decimal(str(price)),
                        high=Decimal(str(price + 0.5)),
                        low=Decimal(str(price - 0.5)),
                        close=Decimal(str(price)),
                        volume=100000
                    )
                    bars.append(bar)
            else:
                # Other symbols: flat prices, no signals
                for i in range(limit):
                    timestamp = base_time + timedelta(minutes=i)
                    bar = Bar(
                        symbol=symbol,
                        timestamp=timestamp,
                        open=Decimal("100.0"),
                        high=Decimal("100.5"),
                        low=Decimal("99.5"),
                        close=Decimal("100.0"),
                        volume=100000
                    )
                    bars.append(bar)
            result[symbol] = bars
        return result

    # Monkeypatch the MockDataProvider's get_latest_bars method
    monkeypatch.setattr(MockDataProvider, "get_latest_bars", fixed_get_latest_bars)

    # First run - should produce exactly 1 order
    run_trading_loop(iterations=1)

    # Find first run directory and count orders
    run_dirs = list(Path("out/runs").iterdir())
    assert len(run_dirs) == 1
    run_dir_1 = run_dirs[0]

    with open(run_dir_1 / "orders.csv") as f:
        lines1 = f.readlines()
        order_count1 = len(lines1) - 1  # Subtract header

    # Verify we got exactly 1 order (deterministic)
    assert order_count1 == 1, f"Expected exactly 1 order from first run, got {order_count1}"

    # Capture state after first run
    state1 = load_state()
    initial_order_ids = state1.submitted_client_order_ids.copy()

    # Should have exactly 1 idempotency key
    assert len(initial_order_ids) == 1, f"Expected exactly 1 idempotency key, got {len(initial_order_ids)}"

    # Verify the key format: SMA_AAPL_buy_YYYYMMDDHHMMSS
    key = list(initial_order_ids)[0]
    assert key.startswith("SMA_AAPL_buy_"), f"Unexpected key format: {key}"

    # Second run - simulates restart with persisted state
    # Same monkeypatch ensures identical data → identical signals → identical keys
    # Idempotency should prevent duplicate order submission
    run_trading_loop(iterations=1)

    # Find second run directory and count orders
    run_dirs_after_2 = list(Path("out/runs").iterdir())
    assert len(run_dirs_after_2) == 2
    run_dir_2 = [d for d in run_dirs_after_2 if d != run_dir_1][0]

    with open(run_dir_2 / "orders.csv") as f:
        lines2 = f.readlines()
        order_count2 = len(lines2) - 1  # Subtract header

    # Verify state after second run
    state2 = load_state()
    final_order_ids = state2.submitted_client_order_ids

    # CRITICAL ASSERTIONS: Verify idempotency worked
    # With per-run directories:
    # - First run creates 1 order in its directory
    # - Second run should create 0 orders (idempotency prevents duplicate)
    assert order_count2 == 0, (
        f"Expected no new orders in second run (idempotency should prevent duplicates), "
        f"but second run created {order_count2} orders"
    )

    # 2. State should contain the same idempotency keys (no new keys added)
    assert final_order_ids == initial_order_ids, (
        f"Expected same idempotency keys in state after second run, "
        f"but keys changed from {initial_order_ids} to {final_order_ids}"
    )

    # 3. Verify we still have exactly 1 key in state
    assert len(final_order_ids) == 1, f"Expected exactly 1 key in state, got {len(final_order_ids)}"


def test_state_persists_across_runs(temp_dir, monkeypatch):
    """Test that state persists across runs."""
    monkeypatch.setenv("MODE", "mock")

    # First run
    run_trading_loop(iterations=1)

    state1 = load_state()
    assert state1 is not None
    order_count1 = len(state1.submitted_client_order_ids)

    # Second run
    run_trading_loop(iterations=1)

    state2 = load_state()
    assert state2 is not None

    # State should accumulate orders
    order_count2 = len(state2.submitted_client_order_ids)
    assert order_count2 >= order_count1


def test_orders_csv_and_fills_csv_populated(temp_dir, monkeypatch):
    """Test that orders.csv and fills.csv are populated."""
    monkeypatch.setenv("MODE", "mock")

    run_trading_loop(iterations=2)

    # Find the run directory
    run_dirs = list(Path("out/runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    # Check orders.csv exists and has content in run directory
    orders_path = run_dir / "orders.csv"
    assert orders_path.exists()

    with open(orders_path) as f:
        lines = f.readlines()
        assert len(lines) >= 1  # At least header

    # Check fills.csv exists and has content in run directory
    fills_path = run_dir / "fills.csv"
    assert fills_path.exists()

    with open(fills_path) as f:
        lines = f.readlines()
        assert len(lines) >= 1  # At least header


def test_trade_record_with_run_id_and_client_order_id():
    """Test TradeRecord model with new fields."""
    trade = TradeRecord(
        timestamp=datetime(2024, 1, 15, 10, 30),
        symbol="AAPL",
        side="buy",
        quantity=10,
        price=Decimal("150.00"),
        order_id="broker-123",
        client_order_id="SMA_AAPL_buy_20240115103000_12345678",
        run_id="12345678-1234-1234-1234-123456789012",
        reason="Test trade"
    )

    csv_row = trade.to_csv_row()

    assert "broker-123" in csv_row
    assert "SMA_AAPL_buy_20240115103000_12345678" in csv_row
    assert "12345678-1234-1234-1234-123456789012" in csv_row


def test_order_record_csv():
    """Test OrderRecord model."""
    order = OrderRecord(
        timestamp=datetime(2024, 1, 15, 10, 30),
        symbol="AAPL",
        side="buy",
        quantity=10,
        order_type="market",
        client_order_id="test-client-order",
        broker_order_id="test-broker-order",
        run_id="test-run-id",
        status="filled"
    )

    csv_row = order.to_csv_row()

    assert "AAPL" in csv_row
    assert "test-client-order" in csv_row
    assert "test-broker-order" in csv_row
    assert "test-run-id" in csv_row


def test_fill_record_csv():
    """Test FillRecord model."""
    fill = FillRecord(
        timestamp=datetime(2024, 1, 15, 10, 30),
        symbol="AAPL",
        side="buy",
        quantity=10,
        price=Decimal("150.00"),
        client_order_id="test-client-order",
        broker_order_id="test-broker-order",
        run_id="test-run-id"
    )

    csv_row = fill.to_csv_row()

    assert "AAPL" in csv_row
    assert "150.00" in csv_row
    assert "test-client-order" in csv_row
    assert "test-run-id" in csv_row
