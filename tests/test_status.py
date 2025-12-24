"""Tests for operator status/metrics snapshot feature."""

import json
from decimal import Decimal

import pytest

from src.app.state import BotState, get_today_date_eastern, save_state, update_daily_realized_pnl


@pytest.fixture
def temp_state_file(monkeypatch, tmp_path):
    """Create temporary state file for testing."""
    state_file = tmp_path / "state.json"
    monkeypatch.setenv("AI_TRADER_STATE_FILE", str(state_file))
    return state_file


@pytest.fixture
def temp_out_dir(monkeypatch, tmp_path):
    """Create temporary out directory for status output."""
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    # Change working directory to tmp_path so out/ is created there
    import os

    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield out_dir
    os.chdir(original_cwd)


def test_status_works_in_mock_mode(temp_state_file, temp_out_dir):
    """Test that --status works in mock mode without Alpaca credentials."""
    from src.app.__main__ import run_status

    # Initialize state with some data
    state = BotState(run_id="test-run")
    state.daily_date = get_today_date_eastern()
    update_daily_realized_pnl(state, Decimal("-50"))
    save_state(state, temp_state_file)

    # Run status in mock mode (dry-run defaults to mock)
    exit_code = run_status("dry-run")

    # Should succeed
    assert exit_code == 0, "Status should succeed in mock mode"

    # Check JSON output was created
    status_file = temp_out_dir / "status.json"
    assert status_file.exists(), "status.json should be created"

    # Validate JSON content
    with open(status_file) as f:
        data = json.load(f)

    assert "timestamp_utc" in data
    assert "timestamp_eastern" in data
    assert data["mode"] == "dry-run"
    assert "daily_pnl" in data
    assert "session_pnl" in data
    assert "open_positions_count" in data
    assert "open_orders_count" in data
    assert "daily_loss_kill_switch_tripped" in data
    assert "session_loss_kill_switch_tripped" in data


def test_status_reflects_daily_pnl_from_state(temp_state_file, temp_out_dir):
    """Test that status reflects daily PnL loaded from state."""
    from src.app.__main__ import run_status

    # Initialize state with daily loss
    state = BotState(run_id="test-run")
    state.daily_date = get_today_date_eastern()
    update_daily_realized_pnl(state, Decimal("-75.50"))
    save_state(state, temp_state_file)

    # Run status
    exit_code = run_status("dry-run")
    assert exit_code == 0

    # Check JSON output
    status_file = temp_out_dir / "status.json"
    with open(status_file) as f:
        data = json.load(f)

    # Verify daily PnL is reflected
    assert data["daily_pnl"] == -75.50, "Daily PnL should be loaded from state"


def test_status_reflects_session_pnl_as_zero(temp_state_file, temp_out_dir):
    """Test that status reflects session PnL as 0 (not persisted)."""
    from src.app.__main__ import run_status

    # Initialize state with daily loss
    state = BotState(run_id="test-run")
    state.daily_date = get_today_date_eastern()
    update_daily_realized_pnl(state, Decimal("-100"))
    save_state(state, temp_state_file)

    # Run status
    exit_code = run_status("dry-run")
    assert exit_code == 0

    # Check JSON output
    status_file = temp_out_dir / "status.json"
    with open(status_file) as f:
        data = json.load(f)

    # Session PnL should always be 0 on fresh start
    assert data["session_pnl"] == 0.0, "Session PnL should be 0 (not persisted)"
    assert data["daily_pnl"] == -100.0, "Daily PnL should be loaded from state"


def test_status_reflects_daily_kill_switch_tripped(temp_state_file, temp_out_dir):
    """Test that status correctly reflects daily loss kill-switch status."""
    from src.app.__main__ import run_status

    # Initialize state with loss exceeding default limit ($500)
    state = BotState(run_id="test-run")
    state.daily_date = get_today_date_eastern()
    update_daily_realized_pnl(state, Decimal("-600"))  # Exceeds $500 limit
    save_state(state, temp_state_file)

    # Run status
    exit_code = run_status("dry-run")
    assert exit_code == 0

    # Check JSON output
    status_file = temp_out_dir / "status.json"
    with open(status_file) as f:
        data = json.load(f)

    # Daily kill-switch should be tripped
    assert data["daily_loss_kill_switch_tripped"] is True, "Daily kill-switch should be tripped"
    assert data["daily_pnl"] == -600.0


def test_status_reflects_daily_kill_switch_not_tripped(temp_state_file, temp_out_dir):
    """Test that status correctly reflects daily loss kill-switch not tripped."""
    from src.app.__main__ import run_status

    # Initialize state with loss under limit
    state = BotState(run_id="test-run")
    state.daily_date = get_today_date_eastern()
    update_daily_realized_pnl(state, Decimal("-400"))  # Under $500 limit
    save_state(state, temp_state_file)

    # Run status
    exit_code = run_status("dry-run")
    assert exit_code == 0

    # Check JSON output
    status_file = temp_out_dir / "status.json"
    with open(status_file) as f:
        data = json.load(f)

    # Daily kill-switch should NOT be tripped
    assert data["daily_loss_kill_switch_tripped"] is False, (
        "Daily kill-switch should not be tripped"
    )
    assert data["daily_pnl"] == -400.0


def test_status_reflects_session_kill_switch_not_tripped(temp_state_file, temp_out_dir):
    """Test that status reflects session kill-switch as not tripped (session PnL always 0 on start)."""
    from src.app.__main__ import run_status

    # Even with daily loss, session PnL is 0 on fresh start
    state = BotState(run_id="test-run")
    state.daily_date = get_today_date_eastern()
    update_daily_realized_pnl(state, Decimal("-100"))
    save_state(state, temp_state_file)

    # Run status
    exit_code = run_status("dry-run")
    assert exit_code == 0

    # Check JSON output
    status_file = temp_out_dir / "status.json"
    with open(status_file) as f:
        data = json.load(f)

    # Session kill-switch should NOT be tripped (session PnL is 0)
    assert data["session_loss_kill_switch_tripped"] is False, (
        "Session kill-switch should not be tripped (session PnL is 0)"
    )
    assert data["session_pnl"] == 0.0


def test_status_reflects_open_positions_count(temp_state_file, temp_out_dir):
    """Test that status reflects correct open positions count from mock broker."""
    from src.app.__main__ import run_status

    # Initialize state
    state = BotState(run_id="test-run")
    state.daily_date = get_today_date_eastern()
    save_state(state, temp_state_file)

    # MockBroker returns empty positions by default
    exit_code = run_status("dry-run")
    assert exit_code == 0

    # Check JSON output
    status_file = temp_out_dir / "status.json"
    with open(status_file) as f:
        data = json.load(f)

    # MockBroker has no positions by default
    assert data["open_positions_count"] == 0, "Mock broker should have 0 positions"
    assert len(data["positions"]) == 0


def test_status_reflects_open_orders_count(temp_state_file, temp_out_dir):
    """Test that status reflects correct open orders count from mock broker."""
    from src.app.__main__ import run_status

    # Initialize state
    state = BotState(run_id="test-run")
    state.daily_date = get_today_date_eastern()
    save_state(state, temp_state_file)

    # MockBroker returns empty orders by default
    exit_code = run_status("dry-run")
    assert exit_code == 0

    # Check JSON output
    status_file = temp_out_dir / "status.json"
    with open(status_file) as f:
        data = json.load(f)

    # MockBroker has no open orders by default
    assert data["open_orders_count"] == 0, "Mock broker should have 0 open orders"
    assert len(data["orders"]) == 0


def test_status_json_has_all_required_fields(temp_state_file, temp_out_dir):
    """Test that status JSON output contains all required fields."""
    from src.app.__main__ import run_status

    # Initialize state
    state = BotState(run_id="test-run")
    state.daily_date = get_today_date_eastern()
    save_state(state, temp_state_file)

    # Run status
    exit_code = run_status("dry-run")
    assert exit_code == 0

    # Check JSON output
    status_file = temp_out_dir / "status.json"
    with open(status_file) as f:
        data = json.load(f)

    # Verify all required fields are present
    required_fields = [
        "timestamp_utc",
        "timestamp_eastern",
        "mode",
        "daily_pnl",
        "session_pnl",
        "open_positions_count",
        "open_orders_count",
        "daily_loss_kill_switch_tripped",
        "session_loss_kill_switch_tripped",
        "positions",
        "orders",
        "last_signals",
    ]

    for field in required_fields:
        assert field in data, f"Field '{field}' should be in status JSON"


def test_status_timestamps_are_valid_iso_format(temp_state_file, temp_out_dir):
    """Test that status timestamps are in valid ISO format."""
    from datetime import datetime

    from src.app.__main__ import run_status

    # Initialize state
    state = BotState(run_id="test-run")
    state.daily_date = get_today_date_eastern()
    save_state(state, temp_state_file)

    # Run status
    exit_code = run_status("dry-run")
    assert exit_code == 0

    # Check JSON output
    status_file = temp_out_dir / "status.json"
    with open(status_file) as f:
        data = json.load(f)

    # Verify timestamps can be parsed
    try:
        datetime.fromisoformat(data["timestamp_utc"])
        datetime.fromisoformat(data["timestamp_eastern"])
    except ValueError as e:
        pytest.fail(f"Timestamps should be valid ISO format: {e}")
