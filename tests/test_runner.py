"""Tests for strategy runner in shadow mode."""

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.app.runner import _create_mock_market_data, run_shadow_mode


def test_create_mock_market_data():
    """Test mock market data generation."""
    universe = ["SPY", "QQQ", "AAPL"]

    market_data = _create_mock_market_data(universe)

    assert len(market_data) == 3
    assert "SPY" in market_data
    assert "QQQ" in market_data
    assert "AAPL" in market_data

    # Check data structure
    for symbol in universe:
        assert "price" in market_data[symbol]
        assert "ma" in market_data[symbol]
        assert "zscore" in market_data[symbol]
        assert market_data[symbol]["price"] > 0
        assert market_data[symbol]["ma"] > 0


def test_run_shadow_mode_with_mock_data(monkeypatch, tmp_path):
    """Test running shadow mode with mocked config and data."""
    # Mock config
    mock_config = MagicMock()
    mock_config.timeframe = "1h"
    mock_config.universe_symbols = ["SPY", "QQQ"]
    mock_config.allowed_symbols = ["SPY", "QQQ"]
    mock_config.max_order_notional = 100
    mock_config.max_daily_loss = 250
    mock_config.max_positions_notional = 10000

    # Use tmp_path for logs
    monkeypatch.setattr("src.app.runner.Path", lambda x: tmp_path if x == "logs" else Path(x))

    with (
        patch("src.app.runner.load_config_with_yaml", return_value=mock_config),
        patch("src.app.runner._create_mock_market_data") as mock_market_data,
    ):
        # Set up mock market data
        mock_market_data.return_value = {
            "SPY": {"price": 450.0, "ma": 440.0, "zscore": -0.5},
            "QQQ": {"price": 380.0, "ma": 385.0, "zscore": 1.2},
        }

        # Run shadow mode (should not raise)
        # Note: This will print to stdout, but that's expected
        # Suppress SystemExit if the run completes successfully
        with contextlib.suppress(SystemExit):
            run_shadow_mode()


def test_run_shadow_mode_exits_with_no_universe(monkeypatch):
    """Test that runner exits gracefully with no symbols in universe."""
    mock_config = MagicMock()
    mock_config.timeframe = "1h"
    mock_config.universe_symbols = []
    mock_config.allowed_symbols = []
    mock_config.max_order_notional = 100
    mock_config.max_daily_loss = 250
    mock_config.max_positions_notional = 10000

    with patch("src.app.runner.load_config_with_yaml", return_value=mock_config):
        with pytest.raises(SystemExit) as exc_info:
            run_shadow_mode()

        assert exc_info.value.code == 1
