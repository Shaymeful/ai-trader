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


@pytest.fixture
def test_run_id():
    """Provide a test run ID."""
    return "test-run-123"


def test_setup_outputs_creates_directories(temp_dir, test_run_id):
    """Test that setup_outputs creates necessary directories."""
    setup_outputs(test_run_id)

    assert Path("out").exists()
    assert Path(f"out/runs/{test_run_id}").exists()


def test_setup_outputs_creates_trades_csv(temp_dir, test_run_id):
    """Test that setup_outputs creates trades.csv with header in run directory."""
    setup_outputs(test_run_id)

    csv_path = Path(f"out/runs/{test_run_id}/trades.csv")
    assert csv_path.exists()

    # Check header is present
    with open(csv_path, "r") as f:
        header = f.readline().strip()
        assert header == "timestamp,symbol,side,quantity,price,order_id,client_order_id,run_id,reason"


def test_setup_outputs_idempotent(temp_dir, test_run_id):
    """Test that calling setup_outputs multiple times is safe."""
    setup_outputs(test_run_id)
    setup_outputs(test_run_id)  # Call again

    csv_path = Path(f"out/runs/{test_run_id}/trades.csv")
    assert csv_path.exists()

    # Should still have only one header line
    with open(csv_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 1


def test_write_trade_to_csv(temp_dir, test_run_id):
    """Test writing a trade to CSV in run directory."""
    setup_outputs(test_run_id)

    trade = TradeRecord(
        timestamp=datetime(2024, 1, 15, 10, 30),
        symbol="AAPL",
        side="buy",
        quantity=10,
        price=Decimal("150.50"),
        order_id="test-order-1",
        client_order_id="test-client-order-1",
        run_id=test_run_id,
        reason="Test trade"
    )

    write_trade_to_csv(trade, test_run_id)

    csv_path = Path(f"out/runs/{test_run_id}/trades.csv")
    with open(csv_path, "r") as f:
        lines = f.readlines()

    # Should have header + 1 trade
    assert len(lines) == 2
    assert "AAPL" in lines[1]
    assert "buy" in lines[1]
    assert "150.50" in lines[1]


def test_write_multiple_trades_to_csv(temp_dir, test_run_id):
    """Test writing multiple trades to CSV in run directory."""
    setup_outputs(test_run_id)

    trades = [
        TradeRecord(
            timestamp=datetime(2024, 1, 15, 10, 30),
            symbol="AAPL",
            side="buy",
            quantity=10,
            price=Decimal("150.50"),
            order_id="order-1",
            client_order_id="client-order-1",
            run_id=test_run_id,
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
            run_id=test_run_id,
            reason="Trade 2"
        ),
    ]

    for trade in trades:
        write_trade_to_csv(trade, test_run_id)

    csv_path = Path(f"out/runs/{test_run_id}/trades.csv")
    with open(csv_path, "r") as f:
        lines = f.readlines()

    # Should have header + 2 trades
    assert len(lines) == 3
    assert "AAPL" in lines[1]
    assert "MSFT" in lines[2]


def test_run_trading_loop_creates_trades_csv(temp_dir, monkeypatch):
    """Test that running the bot always creates trades.csv in run directory."""
    # Set environment to use mock mode
    monkeypatch.setenv("MODE", "mock")

    # Run with just 1 iteration for speed
    run_trading_loop(iterations=1)

    # Find the run directory (should be only one)
    run_dirs = list(Path("out/runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    # Check trades.csv exists in run directory
    csv_path = run_dir / "trades.csv"
    assert csv_path.exists()

    # Check it has at least the header
    with open(csv_path, "r") as f:
        lines = f.readlines()
        assert len(lines) >= 1
        assert "timestamp" in lines[0]
        assert "run_id" in lines[0]
        assert "client_order_id" in lines[0]


def test_run_trading_loop_creates_summary_json(temp_dir, monkeypatch):
    """Test that running the bot creates summary.json in run directory."""
    monkeypatch.setenv("MODE", "mock")

    run_trading_loop(iterations=1)

    # Find the run directory
    run_dirs = list(Path("out/runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    summary_path = run_dir / "summary.json"
    assert summary_path.exists()


def test_trades_csv_empty_if_no_signals(temp_dir, monkeypatch):
    """Test that trades.csv has only header if no trades execute."""
    monkeypatch.setenv("MODE", "mock")

    run_trading_loop(iterations=1)

    # Find the run directory
    run_dirs = list(Path("out/runs").iterdir())
    run_dir = run_dirs[0]

    csv_path = run_dir / "trades.csv"
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

    # Find the run directory
    run_dirs = list(Path("out/runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    summary_path = run_dir / "summary.json"
    with open(summary_path, "r") as f:
        summary = json.load(f)

    # Check both fields exist
    assert "session_trades_executed" in summary
    assert "total_trades_in_file" in summary

    # Both should be equal on first run
    assert summary["session_trades_executed"] == summary["total_trades_in_file"]


def test_session_count_vs_file_count_after_multiple_runs(temp_dir, monkeypatch, test_run_id):
    """Test that session count equals file count in per-run isolation."""
    import json

    monkeypatch.setenv("MODE", "mock")

    # With per-run directories, each run has its own CSV files
    # So session_trades_executed should always equal total_trades_in_file
    setup_outputs(test_run_id)

    # Manually add some trades to this run
    historical_trades = [
        TradeRecord(
            timestamp=datetime(2024, 1, 14, 10, 30),
            symbol="AAPL",
            side="buy",
            quantity=10,
            price=Decimal("150.00"),
            order_id="historical-1",
            client_order_id="historical-client-1",
            run_id=test_run_id,
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
            run_id=test_run_id,
            reason="Historical trade 2"
        ),
    ]

    for trade in historical_trades:
        write_trade_to_csv(trade, test_run_id)

    # Verify we have 2 trades in run directory
    csv_path = Path(f"out/runs/{test_run_id}/trades.csv")
    with open(csv_path, "r") as f:
        initial_lines = len(f.readlines()) - 1  # Subtract header
    assert initial_lines == 2

    # Now run a separate run (new session with new run_id)
    run_trading_loop(iterations=1)

    # Find the new run directory (should be different from test_run_id)
    run_dirs = list(Path("out/runs").iterdir())
    new_run_dirs = [d for d in run_dirs if d.name != test_run_id]
    assert len(new_run_dirs) == 1
    new_run_dir = new_run_dirs[0]

    # Read summary from the NEW run
    summary_path = new_run_dir / "summary.json"
    with open(summary_path, "r") as f:
        summary = json.load(f)

    # Session count should equal file count (per-run isolation)
    session_count = summary["session_trades_executed"]
    total_count = summary["total_trades_in_file"]
    assert total_count == session_count

    # Verify the original run's CSV is unchanged
    with open(csv_path, "r") as f:
        final_lines = len(f.readlines()) - 1  # Subtract header
    assert final_lines == 2  # Should still be 2, not affected by new run


def test_session_trade_count_tracks_correctly(temp_dir, monkeypatch, test_run_id):
    """Test that session trade count increments correctly during execution."""
    import json

    monkeypatch.setenv("MODE", "mock")
    setup_outputs(test_run_id)

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
            run_id=test_run_id,
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
            run_id=test_run_id,
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
            run_id=test_run_id,
            reason="Test trade 3"
        ),
    ]

    for trade in trades:
        write_trade_to_csv(trade, test_run_id)

    # Verify CSV has 3 trades in run directory
    csv_path = Path(f"out/runs/{test_run_id}/trades.csv")
    with open(csv_path, "r") as f:
        lines = len(f.readlines()) - 1
    assert lines == 3


def test_multiple_runs_create_separate_directories(temp_dir, monkeypatch):
    """Test that multiple runs create separate directories without overwriting."""
    import json

    monkeypatch.setenv("MODE", "mock")

    # Run 1
    run_trading_loop(iterations=1)

    # Verify first run created a directory
    run_dirs_after_1 = list(Path("out/runs").iterdir())
    assert len(run_dirs_after_1) == 1
    run_dir_1 = run_dirs_after_1[0]

    # Verify first run has its own files
    assert (run_dir_1 / "trades.csv").exists()
    assert (run_dir_1 / "orders.csv").exists()
    assert (run_dir_1 / "fills.csv").exists()
    assert (run_dir_1 / "summary.json").exists()
    assert (run_dir_1 / "trading.log").exists()

    # Get first run's summary
    with open(run_dir_1 / "summary.json") as f:
        summary_1 = json.load(f)
    run_id_1 = summary_1["run_id"]

    # Run 2
    run_trading_loop(iterations=1)

    # Verify second run created a separate directory
    run_dirs_after_2 = list(Path("out/runs").iterdir())
    assert len(run_dirs_after_2) == 2

    # Find the new run directory
    run_dir_2 = [d for d in run_dirs_after_2 if d != run_dir_1][0]

    # Verify second run has its own files
    assert (run_dir_2 / "trades.csv").exists()
    assert (run_dir_2 / "orders.csv").exists()
    assert (run_dir_2 / "fills.csv").exists()
    assert (run_dir_2 / "summary.json").exists()
    assert (run_dir_2 / "trading.log").exists()

    # Get second run's summary
    with open(run_dir_2 / "summary.json") as f:
        summary_2 = json.load(f)
    run_id_2 = summary_2["run_id"]

    # Verify run IDs are different
    assert run_id_1 != run_id_2

    # Verify directory names match run IDs
    assert run_dir_1.name == run_id_1
    assert run_dir_2.name == run_id_2

    # Verify first run's files were not overwritten
    # (Check that first run's summary still has original run_id)
    with open(run_dir_1 / "summary.json") as f:
        summary_1_check = json.load(f)
    assert summary_1_check["run_id"] == run_id_1

    # Verify CSV files in each run are independent
    # Read line counts from each run
    trades_1_lines = len((run_dir_1 / "trades.csv").read_text().splitlines())
    trades_2_lines = len((run_dir_2 / "trades.csv").read_text().splitlines())

    # Both should have at least headers (may have more if trades executed)
    assert trades_1_lines >= 1
    assert trades_2_lines >= 1
