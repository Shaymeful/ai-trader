"""Tests for YAML configuration loading."""

import tempfile
from decimal import Decimal
from pathlib import Path

from src.app.config import load_config_with_yaml, load_yaml_config


def test_load_yaml_config_with_valid_file():
    """Test loading a valid YAML config file."""
    yaml_content = """
timeframe: "1h"
risk:
  max_order_usd: 100
  max_daily_loss_usd: 250
  max_gross_exposure_usd: 10000
universe:
  core:
    symbols:
      - SPY
      - QQQ
      - AAPL
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        temp_path = Path(f.name)

    try:
        config_dict = load_yaml_config(temp_path)

        assert config_dict["timeframe"] == "1h"
        assert config_dict["risk"]["max_order_usd"] == 100
        assert config_dict["risk"]["max_daily_loss_usd"] == 250
        assert config_dict["risk"]["max_gross_exposure_usd"] == 10000
        assert config_dict["universe"]["core"]["symbols"] == ["SPY", "QQQ", "AAPL"]
    finally:
        temp_path.unlink()


def test_load_yaml_config_with_missing_file():
    """Test loading YAML config when file doesn't exist."""
    config_dict = load_yaml_config(Path("/nonexistent/path/config.yaml"))
    assert config_dict == {}


def test_load_config_with_yaml_merges_values(monkeypatch):
    """Test that YAML values are merged with environment config."""
    # Set minimal environment
    monkeypatch.setenv("MODE", "mock")

    yaml_content = """
timeframe: "15m"
risk:
  max_order_usd: 200
  max_daily_loss_usd: 500
universe:
  core:
    symbols:
      - TSLA
      - NVDA
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        temp_path = Path(f.name)

    try:
        config = load_config_with_yaml(temp_path)

        # Check YAML values were applied
        assert config.timeframe == "15m"
        assert config.max_order_notional == Decimal("200")
        assert config.max_daily_loss == Decimal("500")
        assert config.universe_symbols == ["TSLA", "NVDA"]
    finally:
        temp_path.unlink()


def test_load_config_with_yaml_uses_defaults_when_yaml_missing(monkeypatch):
    """Test that config works even without YAML file."""
    monkeypatch.setenv("MODE", "mock")

    # Load config without YAML (will use defaults)
    config = load_config_with_yaml(Path("/nonexistent/config.yaml"))

    # Should have default values
    assert config.timeframe == "1h"  # Default from Config class
    assert config.mode == "mock"
