"""Tests for strategy runner in shadow mode."""

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.app.data_providers.hourly_provider import MockMarketDataProvider
from src.app.runner import run_shadow_mode


def test_mock_market_data_provider():
    """Test mock market data provider generates correct structure."""
    provider = MockMarketDataProvider(seed=42)
    universe = ["SPY", "QQQ", "AAPL"]

    market_data = provider.get_market_data(universe)

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
    """Test running shadow mode with injected mock provider."""
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

    # Create mock provider
    mock_provider = MockMarketDataProvider(seed=42)

    with (
        patch("src.app.runner.load_config_with_yaml", return_value=mock_config),
        contextlib.suppress(SystemExit),
    ):
        # Run shadow mode with injected provider (should not raise or hit network)
        # Note: This will print to stdout, but that's expected
        run_shadow_mode(provider=mock_provider)


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
