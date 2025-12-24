"""Tests for dry-run execution preview feature."""

import contextlib
from unittest.mock import MagicMock, patch

import pytest

from src.app.__main__ import main


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment for testing."""
    # Remove any live trading env vars
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    # Set test exchange time to market hours
    monkeypatch.setenv("AI_TRADER_EXCHANGE_TIME", "2024-01-15T10:00:00-05:00")


def test_dry_run_does_not_submit_orders(clean_env, monkeypatch, tmp_path):
    """Test that dry-run mode does not submit orders to broker."""
    monkeypatch.setenv("AI_TRADER_STATE_FILE", str(tmp_path / "state.json"))

    with patch("src.app.__main__.MockBroker") as mock_broker_class:
        mock_broker = MagicMock()
        mock_broker.submit_order.return_value = None
        mock_broker_class.return_value = mock_broker

        with (
            patch("sys.argv", ["ai-trader", "--mode", "dry-run", "--dry-run", "--once"]),
            contextlib.suppress(SystemExit),
        ):
            main()

        # Verify submit_order was never called
        mock_broker.submit_order.assert_not_called()


def test_dry_run_produces_output(clean_env, monkeypatch, tmp_path, capsys):
    """Test that dry-run mode produces preview output."""
    monkeypatch.setenv("AI_TRADER_STATE_FILE", str(tmp_path / "state.json"))

    with (
        patch("sys.argv", ["ai-trader", "--mode", "dry-run", "--dry-run", "--once"]),
        contextlib.suppress(SystemExit),
    ):
        main()

    captured = capsys.readouterr()

    # Check for banner
    assert "DRY RUN — NO ORDERS SUBMITTED" in captured.out

    # Check for preview table
    assert "PREVIEW:" in captured.out
    assert "Symbol" in captured.out
    assert "Act" in captured.out
    assert "Qty" in captured.out
    assert "Price" in captured.out
    assert "Reason" in captured.out


def test_live_dry_run_no_safety_gates(clean_env, monkeypatch, tmp_path):
    """Test that live mode + dry-run does not require safety gates."""
    monkeypatch.setenv("AI_TRADER_STATE_FILE", str(tmp_path / "state.json"))
    # Explicitly remove safety flags
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)

    # This should NOT raise ValueError about missing safety flags
    with patch("sys.argv", ["ai-trader", "--mode", "live", "--dry-run", "--once"]):
        try:
            main()
        except SystemExit as e:
            # Should exit cleanly, not raise ValueError
            assert e.code in (0, None)


def test_paper_dry_run_no_credentials(clean_env, monkeypatch, tmp_path):
    """Test that paper mode + dry-run does not require Alpaca credentials."""
    monkeypatch.setenv("AI_TRADER_STATE_FILE", str(tmp_path / "state.json"))
    # Explicitly remove API credentials
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    # This should NOT raise error about missing credentials
    with patch("sys.argv", ["ai-trader", "--mode", "paper", "--dry-run", "--once"]):
        try:
            main()
        except SystemExit as e:
            # Should exit cleanly, not raise error about credentials
            assert e.code in (0, None)


def test_dry_run_with_mock_mode(clean_env, monkeypatch, tmp_path):
    """Test that dry-run works with mock mode."""
    monkeypatch.setenv("AI_TRADER_STATE_FILE", str(tmp_path / "state.json"))

    with patch("sys.argv", ["ai-trader", "--mode", "dry-run", "--dry-run", "--once"]):
        try:
            exit_code = main()
        except SystemExit as e:
            exit_code = e.code

    # Should complete successfully
    assert exit_code in (0, None)


def test_dry_run_shows_decisions(clean_env, monkeypatch, tmp_path, capsys):
    """Test that dry-run shows BUY/SELL/HOLD decisions."""
    monkeypatch.setenv("AI_TRADER_STATE_FILE", str(tmp_path / "state.json"))

    with (
        patch(
            "sys.argv",
            ["ai-trader", "--mode", "dry-run", "--dry-run", "--once", "--symbols", "AAPL,MSFT"],
        ),
        contextlib.suppress(SystemExit),
    ):
        main()

    captured = capsys.readouterr()

    # Should show symbols
    assert "AAPL" in captured.out or "MSFT" in captured.out

    # Should show at least one decision type
    decision_shown = any(d in captured.out for d in ["BUY", "SELL", "HOLD"])
    assert decision_shown, "No decision (BUY/SELL/HOLD) shown in output"


def test_dry_run_skips_broker_calls(clean_env, monkeypatch, tmp_path):
    """Test that dry-run mode uses MockBroker and never calls real broker."""
    monkeypatch.setenv("AI_TRADER_STATE_FILE", str(tmp_path / "state.json"))

    with patch("src.app.__main__.MockBroker") as mock_broker_class:
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker

        with (
            patch("sys.argv", ["ai-trader", "--mode", "dry-run", "--dry-run", "--once"]),
            contextlib.suppress(SystemExit),
        ):
            main()

        # Verify MockBroker was instantiated (dry-run always uses MockBroker)
        mock_broker_class.assert_called()

        # Verify no submit/cancel/replace calls
        mock_broker.submit_order.assert_not_called()
        mock_broker.cancel_order.assert_not_called()


def test_dry_run_flag_overrides_mode(clean_env, monkeypatch, tmp_path):
    """Test that --dry-run flag works with paper and live modes."""
    monkeypatch.setenv("AI_TRADER_STATE_FILE", str(tmp_path / "state.json"))

    # Test with paper mode
    with patch("sys.argv", ["ai-trader", "--mode", "paper", "--dry-run", "--once"]):
        try:
            exit_code = main()
        except SystemExit as e:
            exit_code = e.code

    assert exit_code in (0, None), "Paper + dry-run should succeed"

    # Test with live mode (no safety gates required)
    with patch("sys.argv", ["ai-trader", "--mode", "live", "--dry-run", "--once"]):
        try:
            exit_code = main()
        except SystemExit as e:
            exit_code = e.code

    assert exit_code in (0, None), "Live + dry-run should succeed without safety gates"


def test_dry_run_exit_code_success(clean_env, monkeypatch, tmp_path):
    """Test that dry-run exits with code 0 on success."""
    monkeypatch.setenv("AI_TRADER_STATE_FILE", str(tmp_path / "state.json"))

    with patch("sys.argv", ["ai-trader", "--mode", "dry-run", "--dry-run", "--once"]):
        try:
            exit_code = main()
        except SystemExit as e:
            exit_code = e.code

    assert exit_code in (0, None)


def test_dry_run_with_symbols(clean_env, monkeypatch, tmp_path, capsys):
    """Test that dry-run processes custom symbol list."""
    monkeypatch.setenv("AI_TRADER_STATE_FILE", str(tmp_path / "state.json"))

    with (
        patch(
            "sys.argv",
            ["ai-trader", "--mode", "dry-run", "--dry-run", "--once", "--symbols", "AAPL"],
        ),
        contextlib.suppress(SystemExit),
    ):
        main()

    captured = capsys.readouterr()

    # Should process AAPL
    assert "AAPL" in captured.out
