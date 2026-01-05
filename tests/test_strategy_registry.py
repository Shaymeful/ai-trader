"""Tests for strategy registry system."""

import json
import tempfile
from pathlib import Path

import pytest

from src.app.strategy_registry import StrategyRegistry


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary config directory with base strategies.yaml."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create a minimal strategies.yaml
    config_file = config_dir / "strategies.yaml"
    config_file.write_text(
        """
strategies:
  - strategy_id: "TestStrategy1"
    name: "Test Strategy 1"
    description: "Test strategy"
    enabled: true
    weight: 0.5
    params:
      sma_fast_period: 10
      sma_slow_period: 20
    risk_limits:
      max_position_size: 5000
      max_positions: 3
      max_daily_loss: 500

  - strategy_id: "TestStrategy2"
    name: "Test Strategy 2"
    description: "Another test strategy"
    enabled: false
    weight: 0.5
    params:
      sma_fast_period: 5
      sma_slow_period: 15
    risk_limits:
      max_position_size: 3000
      max_positions: 5
      max_daily_loss: 300

global:
  max_daily_loss: 1000
  max_total_positions: 10
  max_order_notional: 10000
  bar_timeframe: "1Min"
  market_open_hour: 9
  market_open_minute: 30
  market_close_hour: 16
  market_close_minute: 0
"""
    )

    return tmp_path


def test_registry_loads_base_config(temp_config_dir):
    """Test that registry loads base configuration correctly."""
    registry = StrategyRegistry(
        base_config_path=temp_config_dir / "config" / "strategies.yaml",
        overrides_path=temp_config_dir / "out" / "strategies_overrides.json",
    )

    state = registry.get_state()

    # Check strategies loaded
    assert len(state.strategies) == 2
    assert "TestStrategy1" in state.strategies
    assert "TestStrategy2" in state.strategies

    # Check TestStrategy1 config
    strat1 = state.strategies["TestStrategy1"]
    assert strat1.name == "Test Strategy 1"
    assert strat1.enabled is True
    assert strat1.weight == 0.5
    assert strat1.params["sma_fast_period"] == 10
    assert strat1.params["sma_slow_period"] == 20
    assert strat1.active_version == 1
    assert strat1.pending_version is None

    # Check global config
    assert state.global_config.max_daily_loss == 1000
    assert state.global_config.max_total_positions == 10


def test_registry_get_enabled_strategies(temp_config_dir):
    """Test filtering for enabled strategies only."""
    registry = StrategyRegistry(
        base_config_path=temp_config_dir / "config" / "strategies.yaml",
        overrides_path=temp_config_dir / "out" / "strategies_overrides.json",
    )

    enabled = registry.get_enabled_strategies()

    # Only TestStrategy1 is enabled
    assert len(enabled) == 1
    assert enabled[0].strategy_id == "TestStrategy1"


def test_registry_stage_change(temp_config_dir):
    """Test staging a configuration change."""
    registry = StrategyRegistry(
        base_config_path=temp_config_dir / "config" / "strategies.yaml",
        overrides_path=temp_config_dir / "out" / "strategies_overrides.json",
    )

    # Stage a change
    new_version = registry.stage_change("TestStrategy1", {"weight": 0.7})

    # Check pending version was created
    assert new_version == 2
    strat = registry.get_strategy("TestStrategy1")
    assert strat.active_version == 1  # Still active version 1
    assert strat.pending_version == 2  # Pending version 2
    assert strat.weight == 0.7  # Weight updated


def test_registry_activate_pending(temp_config_dir):
    """Test activating pending configuration changes."""
    registry = StrategyRegistry(
        base_config_path=temp_config_dir / "config" / "strategies.yaml",
        overrides_path=temp_config_dir / "out" / "strategies_overrides.json",
    )

    # Stage changes
    registry.stage_change("TestStrategy1", {"weight": 0.8})
    registry.stage_change("TestStrategy2", {"enabled": True})

    # Activate pending versions
    activated = registry.check_and_activate_pending()

    # Check activations
    assert len(activated) == 2
    strategy_ids = {sid for sid, _, _ in activated}
    assert "TestStrategy1" in strategy_ids
    assert "TestStrategy2" in strategy_ids

    # Check versions were activated
    strat1 = registry.get_strategy("TestStrategy1")
    assert strat1.active_version == 2
    assert strat1.pending_version is None

    strat2 = registry.get_strategy("TestStrategy2")
    assert strat2.active_version == 2
    assert strat2.pending_version is None


def test_registry_persists_overrides(temp_config_dir):
    """Test that overrides are persisted to disk."""
    overrides_path = temp_config_dir / "out" / "strategies_overrides.json"

    registry = StrategyRegistry(
        base_config_path=temp_config_dir / "config" / "strategies.yaml",
        overrides_path=overrides_path,
    )

    # Stage a change (this should persist)
    registry.stage_change("TestStrategy1", {"weight": 0.9, "enabled": False})

    # Check file was created
    assert overrides_path.exists()

    # Load overrides and verify
    with open(overrides_path) as f:
        data = json.load(f)

    assert "strategies" in data
    assert "TestStrategy1" in data["strategies"]
    assert data["strategies"]["TestStrategy1"]["weight"] == 0.9
    assert data["strategies"]["TestStrategy1"]["enabled"] is False
    assert data["strategies"]["TestStrategy1"]["pending_version"] == 2


def test_registry_loads_with_overrides(temp_config_dir):
    """Test that registry merges overrides on load."""
    overrides_path = temp_config_dir / "out" / "strategies_overrides.json"
    overrides_path.parent.mkdir(parents=True, exist_ok=True)

    # Create overrides file
    overrides = {
        "strategies": {
            "TestStrategy1": {
                "enabled": False,
                "weight": 0.3,
                "params": {"sma_fast_period": 12},
                "active_version": 1,
                "pending_version": None,
                "last_modified": "2024-01-01T00:00:00+00:00",
            }
        },
        "registry_version": 1,
    }
    with open(overrides_path, "w") as f:
        json.dump(overrides, f)

    # Load registry (should merge overrides)
    registry = StrategyRegistry(
        base_config_path=temp_config_dir / "config" / "strategies.yaml",
        overrides_path=overrides_path,
    )

    # Check overrides were applied
    strat = registry.get_strategy("TestStrategy1")
    assert strat.enabled is False  # Overridden from true
    assert strat.weight == 0.3  # Overridden from 0.5
    assert strat.params["sma_fast_period"] == 12  # Overridden from 10
    assert strat.params["sma_slow_period"] == 20  # Not overridden, kept from base


def test_registry_weight_validation(temp_config_dir):
    """Test that invalid weight values are rejected."""
    registry = StrategyRegistry(
        base_config_path=temp_config_dir / "config" / "strategies.yaml",
        overrides_path=temp_config_dir / "out" / "strategies_overrides.json",
    )

    # Test weight > 1
    with pytest.raises(ValueError, match="Weight must be between 0 and 1"):
        registry.stage_change("TestStrategy1", {"weight": 1.5})

    # Test weight < 0
    with pytest.raises(ValueError, match="Weight must be between 0 and 1"):
        registry.stage_change("TestStrategy1", {"weight": -0.1})


def test_registry_unknown_strategy(temp_config_dir):
    """Test that staging changes to unknown strategy fails."""
    registry = StrategyRegistry(
        base_config_path=temp_config_dir / "config" / "strategies.yaml",
        overrides_path=temp_config_dir / "out" / "strategies_overrides.json",
    )

    with pytest.raises(ValueError, match="Strategy not found"):
        registry.stage_change("NonExistentStrategy", {"weight": 0.5})
