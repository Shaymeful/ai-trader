"""Tests for per-symbol decision logging."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.app.__main__ import run_trading_loop
from src.app.config import Config
from src.app.models import Bar
from src.broker.base import MockBroker
from src.data import MockDataProvider
from src.risk import RiskManager
from src.signals import SMAStrategy


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = MagicMock(spec=Config)
    config.allowed_symbols = ["AAPL"]
    config.max_positions = 4
    config.max_order_quantity = 100
    config.max_daily_loss = 1000
    config.sma_fast_period = 10
    config.sma_slow_period = 30
    config.dry_run = True
    config.market_open_hour = 9
    config.market_open_minute = 30
    config.market_close_hour = 16
    config.market_close_minute = 0
    return config


@pytest.fixture
def mock_components(mock_config):
    """Create mock broker, data provider, and risk manager."""
    broker = MockBroker()
    data_provider = MockDataProvider()
    risk_manager = RiskManager(config=mock_config)
    strategy = SMAStrategy(config=mock_config)
    return broker, data_provider, risk_manager, strategy


def test_decision_logging_insufficient_data_no_crash(mock_config, mock_components):
    """Test decision logging doesn't crash with insufficient data."""
    broker, data_provider, risk_manager, strategy = mock_components

    # Mock data provider to return insufficient bars
    def mock_get_bars(symbols, limit):
        return {
            "AAPL": [
                Bar(
                    symbol="AAPL",
                    timestamp=datetime(2024, 1, 15, 10, 0),
                    open=Decimal("180.0"),
                    high=Decimal("181.0"),
                    low=Decimal("179.0"),
                    close=Decimal("180.5"),
                    volume=100000,
                )
            ]
        }

    data_provider.get_latest_bars = mock_get_bars

    # Should not raise any exceptions
    run_trading_loop(
        config=mock_config,
        broker=broker,
        data_provider=data_provider,
        risk_manager=risk_manager,
        strategy=strategy,
        max_iterations=1,
    )


def test_decision_logging_normal_flow_no_crash(mock_config, mock_components):
    """Test decision logging doesn't crash during normal operation."""
    broker, data_provider, risk_manager, strategy = mock_components

    # Use default MockDataProvider behavior (returns 31 bars)
    # Should not raise any exceptions
    run_trading_loop(
        config=mock_config,
        broker=broker,
        data_provider=data_provider,
        risk_manager=risk_manager,
        strategy=strategy,
        max_iterations=1,
    )
