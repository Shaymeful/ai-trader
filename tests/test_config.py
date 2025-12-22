"""Tests for configuration module."""

import os
from decimal import Decimal

from src.app.config import Config, load_config


def test_config_default_values():
    """Test that Config has sensible defaults."""
    config = Config()

    assert config.mode == "mock"
    assert config.max_positions > 0
    assert config.max_order_quantity > 0
    assert config.max_daily_loss > 0
    assert len(config.allowed_symbols) > 0


def test_config_custom_values():
    """Test creating Config with custom values."""
    config = Config(
        mode="alpaca",
        max_positions=10,
        max_order_quantity=200,
        max_daily_loss=Decimal("2000"),
        allowed_symbols=["AAPL", "MSFT"],
    )

    assert config.mode == "alpaca"
    assert config.max_positions == 10
    assert config.max_order_quantity == 200
    assert config.max_daily_loss == Decimal("2000")
    assert config.allowed_symbols == ["AAPL", "MSFT"]


def test_load_config_with_env_vars(monkeypatch):
    """Test loading config from environment variables."""
    # Set environment variables
    monkeypatch.setenv("MODE", "alpaca")
    monkeypatch.setenv("MAX_POSITIONS", "7")
    monkeypatch.setenv("ALLOWED_SYMBOLS", "AAPL,GOOGL,TSLA")

    config = load_config()

    assert config.mode == "alpaca"
    assert config.max_positions == 7
    assert "AAPL" in config.allowed_symbols
    assert "TSLA" in config.allowed_symbols


def test_load_config_defaults_without_env():
    """Test that load_config works without environment variables."""
    # Clear relevant env vars
    for key in ["MODE", "MAX_POSITIONS", "ALPACA_API_KEY"]:
        if key in os.environ:
            del os.environ[key]

    config = load_config()

    assert config.mode == "mock"
    assert config.max_positions > 0
