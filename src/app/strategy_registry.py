"""Strategy Registry System for tracking and managing multiple strategies.

This module provides a registry that:
1. Loads base strategy configurations from config/strategies.yaml
2. Merges operator overrides from out/strategies_overrides.json
3. Tracks active vs pending versions for next-tick activation
4. Ensures deterministic configuration loading

Key concepts:
- active_version: Currently running configuration version
- pending_version: Configuration staged for next loop tick
- Next-tick activation: Changes only apply at the start of the next trading loop iteration
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass
class StrategyConfig:
    """Configuration for a single strategy."""

    strategy_id: str
    name: str
    description: str
    enabled: bool
    weight: float  # Relative allocation weight (0.0 to 1.0)
    params: dict[str, Any]  # Strategy-specific parameters
    risk_limits: dict[str, float | int]  # Per-strategy risk limits

    # Version tracking
    active_version: int = 1  # Currently active version
    pending_version: int | None = None  # Staged version for next tick
    last_modified: datetime | None = None  # When was this config last changed


@dataclass
class GlobalConfig:
    """Global settings applied to all strategies."""

    max_daily_loss: float
    max_total_positions: int
    max_order_notional: float
    bar_timeframe: str
    market_open_hour: int
    market_open_minute: int
    market_close_hour: int
    market_close_minute: int


@dataclass
class StrategyRegistryState:
    """Complete registry state with all strategies and global config."""

    strategies: dict[str, StrategyConfig]  # strategy_id -> config
    global_config: GlobalConfig
    registry_version: int = 1  # Overall registry version (increments on any change)
    last_activation_check: datetime | None = None  # When did we last check for pending activations


class StrategyRegistry:
    """
    Registry for managing multiple strategy configurations.

    Responsibilities:
    1. Load base configurations from config/strategies.yaml
    2. Apply overrides from out/strategies_overrides.json
    3. Track version changes for next-tick activation
    4. Provide safe modification APIs that stage changes
    """

    def __init__(
        self,
        base_config_path: str | Path = "config/strategies.yaml",
        overrides_path: str | Path = "out/strategies_overrides.json",
    ):
        """
        Initialize strategy registry.

        Args:
            base_config_path: Path to base YAML configuration
            overrides_path: Path to JSON overrides file (may not exist initially)
        """
        self.base_config_path = Path(base_config_path)
        self.overrides_path = Path(overrides_path)
        self.state: StrategyRegistryState | None = None
        self.load()

    def load(self) -> None:
        """
        Load registry state by merging base config and overrides.

        Loading process:
        1. Read base config from YAML
        2. Read overrides from JSON (if exists)
        3. Merge deterministically (overrides take precedence)
        4. Initialize version tracking
        """
        # Load base configuration
        if not self.base_config_path.exists():
            raise FileNotFoundError(f"Base config not found: {self.base_config_path}")

        with open(self.base_config_path) as f:
            base_data = yaml.safe_load(f)

        # Parse strategies
        strategies = {}
        for strat_data in base_data.get("strategies", []):
            strategy_id = strat_data["strategy_id"]
            strategies[strategy_id] = StrategyConfig(
                strategy_id=strategy_id,
                name=strat_data["name"],
                description=strat_data.get("description", ""),
                enabled=strat_data["enabled"],
                weight=strat_data["weight"],
                params=strat_data.get("params", {}),
                risk_limits=strat_data.get("risk_limits", {}),
            )

        # Parse global config
        global_data = base_data.get("global", {})
        global_config = GlobalConfig(
            max_daily_loss=global_data.get("max_daily_loss", 1000),
            max_total_positions=global_data.get("max_total_positions", 10),
            max_order_notional=global_data.get("max_order_notional", 10000),
            bar_timeframe=global_data.get("bar_timeframe", "1Min"),
            market_open_hour=global_data.get("market_open_hour", 9),
            market_open_minute=global_data.get("market_open_minute", 30),
            market_close_hour=global_data.get("market_close_hour", 16),
            market_close_minute=global_data.get("market_close_minute", 0),
        )

        # Load and apply overrides if they exist
        if self.overrides_path.exists():
            with open(self.overrides_path) as f:
                overrides = json.load(f)

            self._apply_overrides(strategies, overrides)

        # Create registry state
        self.state = StrategyRegistryState(
            strategies=strategies,
            global_config=global_config,
        )

    def _apply_overrides(self, strategies: dict[str, StrategyConfig], overrides: dict) -> None:
        """
        Apply overrides from JSON file to strategy configurations.

        Overrides format:
        {
            "strategies": {
                "strategy_id": {
                    "enabled": true/false,
                    "weight": 0.0-1.0,
                    "params": {...},
                    "pending_version": N,
                    "last_modified": "ISO timestamp"
                }
            },
            "registry_version": N
        }
        """
        strategy_overrides = overrides.get("strategies", {})

        for strategy_id, override_data in strategy_overrides.items():
            if strategy_id not in strategies:
                continue  # Skip unknown strategies

            strategy = strategies[strategy_id]

            # Apply overrides
            if "enabled" in override_data:
                strategy.enabled = override_data["enabled"]
            if "weight" in override_data:
                strategy.weight = override_data["weight"]
            if "params" in override_data:
                strategy.params.update(override_data["params"])
            if "pending_version" in override_data:
                strategy.pending_version = override_data["pending_version"]
            if "last_modified" in override_data and override_data["last_modified"] is not None:
                strategy.last_modified = datetime.fromisoformat(override_data["last_modified"])

    def get_strategy(self, strategy_id: str) -> StrategyConfig | None:
        """Get configuration for a specific strategy."""
        if self.state is None:
            return None
        return self.state.strategies.get(strategy_id)

    def get_enabled_strategies(self) -> list[StrategyConfig]:
        """Get all currently enabled strategies."""
        if self.state is None:
            return []
        return [s for s in self.state.strategies.values() if s.enabled]

    def check_and_activate_pending(self) -> list[tuple[str, int, int]]:
        """
        Check for pending versions and activate them.

        This should be called at the START of each trading loop tick.
        Returns list of (strategy_id, old_version, new_version) for activated strategies.
        """
        if self.state is None:
            return []

        activated = []
        now = datetime.now(UTC)

        for strategy_id, strategy in self.state.strategies.items():
            if (
                strategy.pending_version is not None
                and strategy.pending_version > strategy.active_version
            ):
                # Activate the pending version
                old_version = strategy.active_version
                strategy.active_version = strategy.pending_version
                strategy.pending_version = None

                activated.append((strategy_id, old_version, strategy.active_version))

        if activated:
            self.state.last_activation_check = now

        return activated

    def stage_change(self, strategy_id: str, changes: dict[str, Any]) -> int:
        """
        Stage a configuration change for next-tick activation.

        Args:
            strategy_id: Strategy to modify
            changes: Dictionary of changes (enabled, weight, params, etc.)

        Returns:
            New pending version number

        Raises:
            ValueError: If strategy_id not found or changes invalid
        """
        if self.state is None:
            raise ValueError("Registry not loaded")

        strategy = self.state.strategies.get(strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy not found: {strategy_id}")

        # Increment pending version
        new_version = strategy.active_version + 1
        if strategy.pending_version is not None:
            new_version = max(new_version, strategy.pending_version + 1)

        strategy.pending_version = new_version
        strategy.last_modified = datetime.now(UTC)

        # Apply changes to strategy (they'll be effective when activated)
        if "enabled" in changes:
            strategy.enabled = bool(changes["enabled"])
        if "weight" in changes:
            weight = float(changes["weight"])
            if not 0 <= weight <= 1:
                raise ValueError(f"Weight must be between 0 and 1, got {weight}")
            strategy.weight = weight
        if "params" in changes:
            strategy.params.update(changes["params"])

        # Persist to overrides file
        self._save_overrides()

        return new_version

    def _save_overrides(self) -> None:
        """Save current state to overrides file."""
        if self.state is None:
            return

        # Ensure output directory exists
        self.overrides_path.parent.mkdir(parents=True, exist_ok=True)

        # Build overrides structure
        overrides = {
            "strategies": {},
            "registry_version": self.state.registry_version,
            "last_saved": datetime.now(UTC).isoformat(),
        }

        for strategy_id, strategy in self.state.strategies.items():
            overrides["strategies"][strategy_id] = {
                "enabled": strategy.enabled,
                "weight": strategy.weight,
                "params": strategy.params,
                "active_version": strategy.active_version,
                "pending_version": strategy.pending_version,
                "last_modified": strategy.last_modified.isoformat()
                if strategy.last_modified
                else None,
            }

        # Write atomically (write to temp, then rename)
        temp_path = self.overrides_path.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(overrides, f, indent=2)

        temp_path.replace(self.overrides_path)

    def get_state(self) -> StrategyRegistryState:
        """Get current registry state."""
        if self.state is None:
            raise ValueError("Registry not loaded")
        return self.state
