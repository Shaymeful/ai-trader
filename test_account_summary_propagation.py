"""Test that account summary edits propagate system-wide."""

import json
from pathlib import Path

from src.app.strategy_registry import StrategyRegistry


def test_account_summary_propagation():
    """Verify that global_config changes persist and reload correctly."""
    print("Testing account summary propagation...")
    print("=" * 80)

    # Initialize registry (loads from config/strategies.yaml)
    registry = StrategyRegistry(
        base_config_path="config/strategies.yaml",
        overrides_path="out/strategies_overrides.json",
    )

    # Get initial values
    initial_state = registry.get_state()
    initial_max_daily_loss = initial_state.global_config.max_daily_loss
    initial_max_total_positions = initial_state.global_config.max_total_positions
    initial_max_order_notional = initial_state.global_config.max_order_notional

    print("Initial values:")
    print(f"  max_daily_loss: {initial_max_daily_loss}")
    print(f"  max_total_positions: {initial_max_total_positions}")
    print(f"  max_order_notional: {initial_max_order_notional}")
    print()

    # Stage changes
    test_changes = {
        "max_daily_loss": 999.99,
        "max_total_positions": 42,
        "max_order_notional": 7777.77,
    }

    print("Staging changes:")
    for key, value in test_changes.items():
        print(f"  {key}: {value}")

    registry.stage_global_config_change(test_changes)
    print()

    # Verify changes applied in memory
    updated_state = registry.get_state()
    print("After staging (in-memory values):")
    print(f"  max_daily_loss: {updated_state.global_config.max_daily_loss}")
    print(f"  max_total_positions: {updated_state.global_config.max_total_positions}")
    print(f"  max_order_notional: {updated_state.global_config.max_order_notional}")
    print()

    # Verify persisted to overrides file
    overrides_file = Path("out/strategies_overrides.json")
    if overrides_file.exists():
        with open(overrides_file) as f:
            overrides = json.load(f)

        print("Persisted to out/strategies_overrides.json:")
        global_config_overrides = overrides.get("global_config", {})
        print(f"  max_daily_loss: {global_config_overrides.get('max_daily_loss')}")
        print(f"  max_total_positions: {global_config_overrides.get('max_total_positions')}")
        print(f"  max_order_notional: {global_config_overrides.get('max_order_notional')}")
        print()
    else:
        print("WARNING: Overrides file not found!")
        print()

    # Reload registry from disk to verify persistence
    print("Reloading registry from disk...")
    new_registry = StrategyRegistry(
        base_config_path="config/strategies.yaml",
        overrides_path="out/strategies_overrides.json",
    )

    reloaded_state = new_registry.get_state()
    print("After reload (loaded from overrides):")
    print(f"  max_daily_loss: {reloaded_state.global_config.max_daily_loss}")
    print(f"  max_total_positions: {reloaded_state.global_config.max_total_positions}")
    print(f"  max_order_notional: {reloaded_state.global_config.max_order_notional}")
    print()

    # Verify values match
    success = True
    for key, expected_value in test_changes.items():
        actual_value = getattr(reloaded_state.global_config, key)
        if actual_value != expected_value:
            print(f"FAIL: {key} mismatch! Expected {expected_value}, got {actual_value}")
            success = False

    if success:
        print("=" * 80)
        print("SUCCESS: All values persisted and reloaded correctly!")
        print("=" * 80)
    else:
        print("=" * 80)
        print("FAILED: Some values did not persist correctly")
        print("=" * 80)

    # Restore original values
    print()
    print("Restoring original values...")
    restore_changes = {
        "max_daily_loss": initial_max_daily_loss,
        "max_total_positions": initial_max_total_positions,
        "max_order_notional": initial_max_order_notional,
    }
    registry.stage_global_config_change(restore_changes)
    print("Original values restored.")

    return success


if __name__ == "__main__":
    test_account_summary_propagation()
