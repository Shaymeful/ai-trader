"""Tests for loop runner functionality."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.app.runner import RunResult, run_loop


def test_run_loop_executes_multiple_iterations(monkeypatch, tmp_path):
    """Test that run_loop executes multiple iterations before stopping."""
    # Mock time.sleep to avoid actual sleeping
    sleep_calls = []

    def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Stop after 3 iterations
        if len(sleep_calls) >= 3:
            raise KeyboardInterrupt()

    monkeypatch.setattr("time.sleep", mock_sleep)

    # Mock run_shadow_mode to return a result
    mock_result = RunResult(
        mode="shadow",
        dry_run=False,
        orders_placed=0,
        orders_skipped=0,
        strategy_weights={"Trend": 0.5, "MeanRev": 0.5},
        timestamp=datetime.now(UTC).isoformat(),
    )

    call_count = [0]

    def mock_run_shadow():
        call_count[0] += 1
        return mock_result

    monkeypatch.setattr("src.app.runner.run_shadow_mode", mock_run_shadow)

    # Use tmp_path for logs
    monkeypatch.setattr("src.app.runner.Path", lambda x: tmp_path if x == "logs" else Path(x))

    # Run loop (will stop after 3 iterations due to mock_sleep)
    with pytest.raises(SystemExit):  # KeyboardInterrupt causes sys.exit(0)
        run_loop(mode="shadow", dry_run=False, sleep_seconds=10)

    # Verify run_shadow_mode was called 3 times
    assert call_count[0] == 3

    # Verify sleep was called 3 times with correct interval
    assert len(sleep_calls) == 3
    assert all(s == 10 for s in sleep_calls)


def test_run_loop_logs_success_to_status_log(monkeypatch, tmp_path):
    """Test that successful runs are logged to loop_status.log."""

    # Mock time.sleep to stop after 1 iteration
    def mock_sleep(seconds):
        raise KeyboardInterrupt()

    monkeypatch.setattr("time.sleep", mock_sleep)

    # Mock run_shadow_mode
    mock_result = RunResult(
        mode="shadow",
        dry_run=False,
        orders_placed=0,
        orders_skipped=0,
        strategy_weights={"Trend_MA20": 0.55, "MeanRev_Z1.0": 0.45},
        timestamp="2025-12-30T10:00:00+00:00",
    )

    monkeypatch.setattr("src.app.runner.run_shadow_mode", lambda: mock_result)

    # Use tmp_path for logs
    monkeypatch.setattr("src.app.runner.Path", lambda x: tmp_path if x == "logs" else Path(x))

    # Run loop
    with pytest.raises(SystemExit):
        run_loop(mode="shadow", dry_run=False, sleep_seconds=10)

    # Check status log was created
    status_log = tmp_path / "loop_status.log"
    assert status_log.exists()

    # Read and verify content
    content = status_log.read_text()
    assert "SUCCESS" in content
    assert "mode=shadow" in content
    assert "dry_run=False" in content
    assert "orders_placed=0" in content
    assert "orders_skipped=0" in content
    assert "Trend_MA20=55.00%" in content
    assert "MeanRev_Z1.0=45.00%" in content


def test_run_loop_catches_exceptions_and_continues(monkeypatch, tmp_path):
    """Test that exceptions are caught and logged, but loop continues."""
    # Mock time.sleep to stop after 3 iterations
    sleep_calls = []

    def mock_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 3:
            raise KeyboardInterrupt()

    monkeypatch.setattr("time.sleep", mock_sleep)

    # Mock run_shadow_mode to fail on first call, succeed on others
    call_count = [0]

    def mock_run_shadow():
        call_count[0] += 1
        if call_count[0] == 1:
            raise ValueError("Simulated error")
        return RunResult(
            mode="shadow",
            dry_run=False,
            orders_placed=0,
            orders_skipped=0,
            strategy_weights={"Trend": 0.5},
            timestamp=datetime.now(UTC).isoformat(),
        )

    monkeypatch.setattr("src.app.runner.run_shadow_mode", mock_run_shadow)

    # Use tmp_path for logs
    monkeypatch.setattr("src.app.runner.Path", lambda x: tmp_path if x == "logs" else Path(x))

    # Run loop
    with pytest.raises(SystemExit):
        run_loop(mode="shadow", dry_run=False, sleep_seconds=10)

    # Verify run_shadow_mode was called 3 times (despite first failure)
    assert call_count[0] == 3

    # Verify sleep was called 3 times
    assert len(sleep_calls) == 3

    # Check error log was created
    error_log = tmp_path / "loop_errors.log"
    assert error_log.exists()

    # Verify error was logged
    error_content = error_log.read_text()
    assert "ValueError: Simulated error" in error_content
    assert "Traceback" in error_content

    # Check status log contains both ERROR and SUCCESS entries
    status_log = tmp_path / "loop_status.log"
    assert status_log.exists()
    status_content = status_log.read_text()

    # Count entries
    lines = status_content.strip().split("\n")
    assert len(lines) == 3

    # First line should be ERROR
    assert "ERROR" in lines[0]
    assert "ValueError: Simulated error" in lines[0]

    # Other lines should be SUCCESS
    assert "SUCCESS" in lines[1]
    assert "SUCCESS" in lines[2]


def test_run_loop_paper_mode_with_dry_run(monkeypatch, tmp_path):
    """Test that run_loop works with paper mode and dry-run."""

    # Mock time.sleep to stop after 1 iteration
    def mock_sleep(seconds):
        raise KeyboardInterrupt()

    monkeypatch.setattr("time.sleep", mock_sleep)

    # Mock run_paper_mode
    mock_result = RunResult(
        mode="paper",
        dry_run=True,
        orders_placed=5,
        orders_skipped=2,
        strategy_weights={"Trend": 0.6, "MeanRev": 0.4},
        timestamp=datetime.now(UTC).isoformat(),
    )

    monkeypatch.setattr(
        "src.app.runner.run_paper_mode", lambda dry_run, cancel_open_orders=False: mock_result
    )

    # Use tmp_path for logs
    monkeypatch.setattr("src.app.runner.Path", lambda x: tmp_path if x == "logs" else Path(x))

    # Run loop in paper mode with dry-run
    with pytest.raises(SystemExit):
        run_loop(mode="paper", dry_run=True, sleep_seconds=3600)

    # Check status log
    status_log = tmp_path / "loop_status.log"
    assert status_log.exists()

    content = status_log.read_text()
    assert "SUCCESS" in content
    assert "mode=paper" in content
    assert "dry_run=True" in content
    assert "orders_placed=5" in content
    assert "orders_skipped=2" in content
    assert "Trend=60.00%" in content
    assert "MeanRev=40.00%" in content


def test_run_result_dataclass():
    """Test RunResult dataclass structure."""
    result = RunResult(
        mode="shadow",
        dry_run=False,
        orders_placed=0,
        orders_skipped=0,
        strategy_weights={"Test": 1.0},
        timestamp="2025-12-30T10:00:00+00:00",
    )

    assert result.mode == "shadow"
    assert result.dry_run is False
    assert result.orders_placed == 0
    assert result.orders_skipped == 0
    assert result.strategy_weights == {"Test": 1.0}
    assert result.timestamp == "2025-12-30T10:00:00+00:00"


def test_run_loop_handles_empty_strategy_weights(monkeypatch, tmp_path):
    """Test that run_loop handles empty strategy weights gracefully."""

    # Mock time.sleep to stop after 1 iteration
    def mock_sleep(seconds):
        raise KeyboardInterrupt()

    monkeypatch.setattr("time.sleep", mock_sleep)

    # Mock result with no strategy weights (paper mode without dry-run)
    mock_result = RunResult(
        mode="paper",
        dry_run=False,
        orders_placed=3,
        orders_skipped=1,
        strategy_weights={},  # Empty weights
        timestamp=datetime.now(UTC).isoformat(),
    )

    monkeypatch.setattr(
        "src.app.runner.run_paper_mode", lambda dry_run, cancel_open_orders=False: mock_result
    )

    # Use tmp_path for logs
    monkeypatch.setattr("src.app.runner.Path", lambda x: tmp_path if x == "logs" else Path(x))

    # Run loop
    with pytest.raises(SystemExit):
        run_loop(mode="paper", dry_run=False, sleep_seconds=10)

    # Check status log
    status_log = tmp_path / "loop_status.log"
    assert status_log.exists()

    content = status_log.read_text()
    assert "SUCCESS" in content
    assert "weights=[]" in content  # Empty weights shown as []


def test_run_loop_keyboard_interrupt_exits_cleanly(monkeypatch, tmp_path, capsys):
    """Test that KeyboardInterrupt during sleep exits cleanly."""

    # Mock time.sleep to raise KeyboardInterrupt immediately
    def mock_sleep(seconds):
        raise KeyboardInterrupt()

    monkeypatch.setattr("time.sleep", mock_sleep)

    # Mock run_shadow_mode
    mock_result = RunResult(
        mode="shadow",
        dry_run=False,
        orders_placed=0,
        orders_skipped=0,
        strategy_weights={},
        timestamp=datetime.now(UTC).isoformat(),
    )

    monkeypatch.setattr("src.app.runner.run_shadow_mode", lambda: mock_result)

    # Use tmp_path for logs
    monkeypatch.setattr("src.app.runner.Path", lambda x: tmp_path if x == "logs" else Path(x))

    # Run loop - should exit cleanly
    with pytest.raises(SystemExit) as exc_info:
        run_loop(mode="shadow", dry_run=False, sleep_seconds=10)

    # Verify it exits with code 0 (clean shutdown)
    assert exc_info.value.code == 0

    # Verify shutdown message was printed
    captured = capsys.readouterr()
    assert "Keyboard interrupt received" in captured.out
    assert "Shutting down loop mode" in captured.out
