"""Tests for live trading safety gate."""
import os
import tempfile

import pytest

from src.app.config import Config, is_live_trading_mode, load_config
from src.app.__main__ import run_trading_loop


def test_is_live_trading_mode_mock():
    """Test that mock mode is not considered live trading."""
    config = Config(mode="mock")
    assert not is_live_trading_mode(config)


def test_is_live_trading_mode_paper():
    """Test that alpaca paper trading is not considered live trading."""
    config = Config(
        mode="alpaca",
        alpaca_base_url="https://paper-api.alpaca.markets"
    )
    assert not is_live_trading_mode(config)


def test_is_live_trading_mode_live():
    """Test that alpaca live trading is detected."""
    config = Config(
        mode="alpaca",
        alpaca_base_url="https://api.alpaca.markets"
    )
    assert is_live_trading_mode(config)


def test_is_live_trading_mode_live_case_insensitive():
    """Test that live mode detection is case-insensitive."""
    config = Config(
        mode="alpaca",
        alpaca_base_url="https://API.ALPACA.MARKETS"
    )
    assert is_live_trading_mode(config)


def test_live_trading_fails_without_flags(monkeypatch, tmp_path):
    """Test that live trading fails fast without safety flags."""
    # Change to temp directory
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        # Set up live trading mode WITHOUT safety flags
        monkeypatch.setenv("MODE", "alpaca")
        monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
        monkeypatch.setenv("ALPACA_API_KEY", "test-key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
        # Explicitly NOT setting ENABLE_LIVE_TRADING or I_UNDERSTAND_LIVE_TRADING_RISK

        # Should raise ValueError with specific message
        with pytest.raises(ValueError) as excinfo:
            run_trading_loop(iterations=1)

        assert "Live trading disabled" in str(excinfo.value)
        assert "ENABLE_LIVE_TRADING=true" in str(excinfo.value)
        assert "I_UNDERSTAND_LIVE_TRADING_RISK=true" in str(excinfo.value)

    finally:
        os.chdir(original_cwd)


def test_live_trading_fails_with_only_enable_flag(monkeypatch, tmp_path):
    """Test that live trading fails with only ENABLE_LIVE_TRADING set."""
    # Change to temp directory
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        # Set up live trading mode with only one flag
        monkeypatch.setenv("MODE", "alpaca")
        monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
        monkeypatch.setenv("ALPACA_API_KEY", "test-key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
        monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
        # NOT setting I_UNDERSTAND_LIVE_TRADING_RISK

        # Should raise ValueError
        with pytest.raises(ValueError) as excinfo:
            run_trading_loop(iterations=1)

        assert "Live trading disabled" in str(excinfo.value)

    finally:
        os.chdir(original_cwd)


def test_live_trading_fails_with_only_risk_flag(monkeypatch, tmp_path):
    """Test that live trading fails with only I_UNDERSTAND_LIVE_TRADING_RISK set."""
    # Change to temp directory
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        # Set up live trading mode with only one flag
        monkeypatch.setenv("MODE", "alpaca")
        monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
        monkeypatch.setenv("ALPACA_API_KEY", "test-key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
        monkeypatch.setenv("I_UNDERSTAND_LIVE_TRADING_RISK", "true")
        # NOT setting ENABLE_LIVE_TRADING

        # Should raise ValueError
        with pytest.raises(ValueError) as excinfo:
            run_trading_loop(iterations=1)

        assert "Live trading disabled" in str(excinfo.value)

    finally:
        os.chdir(original_cwd)


def test_live_trading_succeeds_with_both_flags(monkeypatch, tmp_path):
    """Test that live trading proceeds when both safety flags are set.

    Note: This test still uses MockBroker (due to NotImplementedError in AlpacaBroker)
    but verifies that the safety gate ALLOWS execution when flags are set.
    """
    # Change to temp directory
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        # Set up live trading mode with BOTH safety flags
        monkeypatch.setenv("MODE", "alpaca")
        monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
        monkeypatch.setenv("ALPACA_API_KEY", "test-key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
        monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
        monkeypatch.setenv("I_UNDERSTAND_LIVE_TRADING_RISK", "true")

        # Should NOT raise ValueError (safety gate passes)
        # Will fall back to MockBroker due to NotImplementedError, but that's OK
        run_trading_loop(iterations=1)

        # Verify summary.json was created (indicating successful run)
        assert (tmp_path / "out" / "summary.json").exists()

    finally:
        os.chdir(original_cwd)


def test_paper_trading_works_without_flags(monkeypatch, tmp_path):
    """Test that paper trading does NOT require safety flags."""
    # Change to temp directory
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        # Set up paper trading mode WITHOUT safety flags
        monkeypatch.setenv("MODE", "alpaca")
        monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        monkeypatch.setenv("ALPACA_API_KEY", "test-key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
        # NOT setting safety flags - should still work for paper trading

        # Should NOT raise ValueError (paper trading is safe by default)
        run_trading_loop(iterations=1)

        # Verify summary.json was created
        assert (tmp_path / "out" / "summary.json").exists()

    finally:
        os.chdir(original_cwd)


def test_mock_mode_works_without_flags(monkeypatch, tmp_path):
    """Test that mock mode does NOT require safety flags."""
    # Change to temp directory
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        # Set up mock mode WITHOUT safety flags
        monkeypatch.setenv("MODE", "mock")
        # NOT setting safety flags - mock mode is always safe

        # Should NOT raise ValueError
        run_trading_loop(iterations=1)

        # Verify summary.json was created
        assert (tmp_path / "out" / "summary.json").exists()

    finally:
        os.chdir(original_cwd)


def test_config_flags_default_to_false():
    """Test that safety flags default to False."""
    config = Config()
    assert config.enable_live_trading is False
    assert config.i_understand_live_trading_risk is False


def test_config_flags_load_from_env(monkeypatch):
    """Test that safety flags load correctly from environment."""
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("I_UNDERSTAND_LIVE_TRADING_RISK", "true")

    config = load_config()

    assert config.enable_live_trading is True
    assert config.i_understand_live_trading_risk is True


def test_config_flags_case_insensitive(monkeypatch):
    """Test that safety flags are case-insensitive."""
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "TRUE")
    monkeypatch.setenv("I_UNDERSTAND_LIVE_TRADING_RISK", "True")

    config = load_config()

    assert config.enable_live_trading is True
    assert config.i_understand_live_trading_risk is True


def test_config_flags_false_values(monkeypatch):
    """Test that non-'true' values are treated as False."""
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")
    monkeypatch.setenv("I_UNDERSTAND_LIVE_TRADING_RISK", "no")

    config = load_config()

    assert config.enable_live_trading is False
    assert config.i_understand_live_trading_risk is False
