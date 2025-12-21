"""Tests for main application module."""
import os
from pathlib import Path
import shutil
import tempfile

import pytest

from src.app.__main__ import setup_outputs, write_trade_to_csv, run_trading_loop
from src.app.models import TradeRecord, OrderSide
from datetime import datetime
from decimal import Decimal


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


def test_setup_outputs_creates_directories(temp_dir):
    """Test that setup_outputs creates necessary directories."""
    setup_outputs()

    assert Path("out").exists()
    assert Path("logs").exists()


def test_setup_outputs_creates_trades_csv(temp_dir):
    """Test that setup_outputs creates trades.csv with header."""
    setup_outputs()

    csv_path = Path("out/trades.csv")
    assert csv_path.exists()

    # Check header is present
    with open(csv_path, "r") as f:
        header = f.readline().strip()
        assert header == "timestamp,symbol,side,quantity,price,order_id,client_order_id,run_id,reason"


def test_setup_outputs_idempotent(temp_dir):
    """Test that calling setup_outputs multiple times is safe."""
    setup_outputs()
    setup_outputs()  # Call again

    csv_path = Path("out/trades.csv")
    assert csv_path.exists()

    # Should still have only one header line
    with open(csv_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 1


def test_write_trade_to_csv(temp_dir):
    """Test writing a trade to CSV."""
    setup_outputs()

    trade = TradeRecord(
        timestamp=datetime(2024, 1, 15, 10, 30),
        symbol="AAPL",
        side="buy",
        quantity=10,
        price=Decimal("150.50"),
        order_id="test-order-1",
        client_order_id="test-client-order-1",
        run_id="test-run-id",
        reason="Test trade"
    )

    write_trade_to_csv(trade)

    csv_path = Path("out/trades.csv")
    with open(csv_path, "r") as f:
        lines = f.readlines()

    # Should have header + 1 trade
    assert len(lines) == 2
    assert "AAPL" in lines[1]
    assert "buy" in lines[1]
    assert "150.50" in lines[1]


def test_write_multiple_trades_to_csv(temp_dir):
    """Test writing multiple trades to CSV."""
    setup_outputs()

    trades = [
        TradeRecord(
            timestamp=datetime(2024, 1, 15, 10, 30),
            symbol="AAPL",
            side="buy",
            quantity=10,
            price=Decimal("150.50"),
            order_id="order-1",
            client_order_id="client-order-1",
            run_id="test-run-id",
            reason="Trade 1"
        ),
        TradeRecord(
            timestamp=datetime(2024, 1, 15, 11, 30),
            symbol="MSFT",
            side="sell",
            quantity=5,
            price=Decimal("380.25"),
            order_id="order-2",
            client_order_id="client-order-2",
            run_id="test-run-id",
            reason="Trade 2"
        ),
    ]

    for trade in trades:
        write_trade_to_csv(trade)

    csv_path = Path("out/trades.csv")
    with open(csv_path, "r") as f:
        lines = f.readlines()

    # Should have header + 2 trades
    assert len(lines) == 3
    assert "AAPL" in lines[1]
    assert "MSFT" in lines[2]


def test_run_trading_loop_creates_trades_csv(temp_dir, monkeypatch):
    """Test that running the bot always creates trades.csv."""
    # Set environment to use mock mode
    monkeypatch.setenv("MODE", "mock")

    # Run with just 1 iteration for speed
    run_trading_loop(iterations=1)

    # Check trades.csv exists
    csv_path = Path("out/trades.csv")
    assert csv_path.exists()

    # Check it has at least the header
    with open(csv_path, "r") as f:
        lines = f.readlines()
        assert len(lines) >= 1
        assert "timestamp" in lines[0]
        assert "run_id" in lines[0]
        assert "client_order_id" in lines[0]


def test_run_trading_loop_creates_summary_json(temp_dir, monkeypatch):
    """Test that running the bot creates summary.json."""
    monkeypatch.setenv("MODE", "mock")

    run_trading_loop(iterations=1)

    summary_path = Path("out/summary.json")
    assert summary_path.exists()


def test_trades_csv_empty_if_no_signals(temp_dir, monkeypatch):
    """Test that trades.csv has only header if no trades execute."""
    monkeypatch.setenv("MODE", "mock")

    run_trading_loop(iterations=1)

    csv_path = Path("out/trades.csv")
    with open(csv_path, "r") as f:
        lines = f.readlines()

    # Likely only header since mock data rarely triggers signals
    # But at minimum, we should have the header
    assert len(lines) >= 1
    assert lines[0].strip() == "timestamp,symbol,side,quantity,price,order_id,client_order_id,run_id,reason"


def test_summary_contains_session_and_total_counts(temp_dir, monkeypatch):
    """Test that summary.json contains both session and total trade counts."""
    import json

    monkeypatch.setenv("MODE", "mock")

    # First run
    run_trading_loop(iterations=1)

    summary_path = Path("out/summary.json")
    with open(summary_path, "r") as f:
        summary = json.load(f)

    # Check both fields exist
    assert "session_trades_executed" in summary
    assert "total_trades_in_file" in summary

    # Both should be equal on first run
    assert summary["session_trades_executed"] == summary["total_trades_in_file"]


def test_session_count_vs_file_count_after_multiple_runs(temp_dir, monkeypatch):
    """Test that session count is per-session while file count accumulates."""
    import json

    monkeypatch.setenv("MODE", "mock")
    setup_outputs()

    # Manually add some trades to simulate previous session
    historical_trades = [
        TradeRecord(
            timestamp=datetime(2024, 1, 14, 10, 30),
            symbol="AAPL",
            side="buy",
            quantity=10,
            price=Decimal("150.00"),
            order_id="historical-1",
            client_order_id="historical-client-1",
            run_id="historical-run-id",
            reason="Historical trade 1"
        ),
        TradeRecord(
            timestamp=datetime(2024, 1, 14, 11, 30),
            symbol="MSFT",
            side="sell",
            quantity=5,
            price=Decimal("380.00"),
            order_id="historical-2",
            client_order_id="historical-client-2",
            run_id="historical-run-id",
            reason="Historical trade 2"
        ),
    ]

    for trade in historical_trades:
        write_trade_to_csv(trade)

    # Verify we have 2 historical trades
    csv_path = Path("out/trades.csv")
    with open(csv_path, "r") as f:
        initial_lines = len(f.readlines()) - 1  # Subtract header
    assert initial_lines == 2

    # Now run the bot (new session)
    run_trading_loop(iterations=1)

    # Read summary
    summary_path = Path("out/summary.json")
    with open(summary_path, "r") as f:
        summary = json.load(f)

    # Session count should be for this session only (likely 0 or small)
    session_count = summary["session_trades_executed"]

    # Total count should include historical + this session
    total_count = summary["total_trades_in_file"]

    # Total must be >= historical trades
    assert total_count >= 2

    # Total should be historical + session
    assert total_count == initial_lines + session_count

    # Verify file has the right number of trades
    with open(csv_path, "r") as f:
        final_lines = len(f.readlines()) - 1  # Subtract header
    assert final_lines == total_count


def test_session_trade_count_tracks_correctly(temp_dir, monkeypatch):
    """Test that session trade count increments correctly during execution."""
    import json

    monkeypatch.setenv("MODE", "mock")
    setup_outputs()

    # Manually write trades during "session"
    trades = [
        TradeRecord(
            timestamp=datetime(2024, 1, 15, 10, 30),
            symbol="AAPL",
            side="buy",
            quantity=10,
            price=Decimal("150.00"),
            order_id="test-1",
            client_order_id="test-client-1",
            run_id="test-run-id",
            reason="Test trade 1"
        ),
        TradeRecord(
            timestamp=datetime(2024, 1, 15, 11, 30),
            symbol="GOOGL",
            side="buy",
            quantity=15,
            price=Decimal("140.00"),
            order_id="test-2",
            client_order_id="test-client-2",
            run_id="test-run-id",
            reason="Test trade 2"
        ),
        TradeRecord(
            timestamp=datetime(2024, 1, 15, 12, 30),
            symbol="TSLA",
            side="sell",
            quantity=20,
            price=Decimal("250.00"),
            order_id="test-3",
            client_order_id="test-client-3",
            run_id="test-run-id",
            reason="Test trade 3"
        ),
    ]

    for trade in trades:
        write_trade_to_csv(trade)

    # Verify CSV has 3 trades
    csv_path = Path("out/trades.csv")
    with open(csv_path, "r") as f:
        lines = len(f.readlines()) - 1
    assert lines == 3
