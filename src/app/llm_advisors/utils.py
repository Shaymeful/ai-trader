"""
Utility functions for AI Co-Pilot.

Includes trading disabled detection, UI runtime overrides, and config precedence logic.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("ai-trader.copilot.utils")


def is_trading_disabled() -> bool:
    """
    Check if trading is disabled via pause flag.

    Returns:
        True if pause_trading.flag exists (trading disabled), False otherwise

    Safety:
        - Never raises exceptions
        - Missing file = False (trading enabled)
    """
    try:
        pause_file = Path("state/pause_trading.flag")
        return pause_file.exists()
    except Exception as e:
        logger.warning(f"Error checking trading disabled status: {e}")
        return False


def load_ui_runtime_overrides() -> dict[str, Any]:
    """
    Load UI runtime overrides from JSON file.

    Returns:
        Dict with overrides, or empty dict if file doesn't exist or is invalid

    Safety:
        - Invalid JSON → log warning and return empty dict
        - Missing file → return empty dict
        - Never raises exceptions
    """
    overrides_path = Path("data/ui_runtime_overrides.json")

    if not overrides_path.exists():
        return {}

    try:
        with open(overrides_path, "r", encoding="utf-8") as f:
            overrides = json.load(f)

        if not isinstance(overrides, dict):
            logger.warning(f"UI runtime overrides is not a dict, ignoring")
            return {}

        return overrides

    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in UI runtime overrides, ignoring: {e}")
        return {}
    except Exception as e:
        logger.warning(f"Error loading UI runtime overrides: {e}")
        return {}


def save_ui_runtime_overrides(overrides: dict[str, Any]) -> bool:
    """
    Save UI runtime overrides to JSON file (atomic write).

    Args:
        overrides: Dict to save

    Returns:
        True if successful, False otherwise

    Safety:
        - Atomic write (temp file → rename)
        - Creates directories as needed
        - Never raises exceptions
    """
    overrides_path = Path("data/ui_runtime_overrides.json")

    try:
        overrides_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp, then rename
        temp_path = overrides_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(overrides, f, indent=2)

        temp_path.replace(overrides_path)

        logger.debug(f"Saved UI runtime overrides: {overrides_path}")
        return True

    except Exception as e:
        logger.error(f"Error saving UI runtime overrides: {e}")
        return False


def validate_ui_overrides(overrides: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate UI runtime overrides contain only safe fields.

    Args:
        overrides: Dict to validate

    Returns:
        Tuple of (is_valid, list_of_errors)

    Safe fields (can be modified by UI):
        - ai_copilot.enabled
        - ai_copilot.dry_run
        - ai_copilot.max_calls_per_run
        - ai_copilot.budgets.global_max_output_tokens
        - ai_copilot.trade_rationale.enabled
        - ai_copilot.daily_journal.enabled
        - ai_copilot.strategy_critique.enabled

    Unsafe fields (MUST NOT be modified by UI):
        - ai_copilot.influence_decisions
        - Any trading logic
        - Strategy weights
        - Order sizing
    """
    errors = []

    # Check for ai_copilot section
    if "ai_copilot" not in overrides:
        return True, []  # No overrides = valid

    ai_copilot = overrides["ai_copilot"]
    if not isinstance(ai_copilot, dict):
        errors.append("ai_copilot must be a dict")
        return False, errors

    # Define safe fields
    safe_root_fields = {
        "enabled",
        "dry_run",
        "max_calls_per_run",
        "budgets",
        "trade_rationale",
        "daily_journal",
        "strategy_critique",
        "universe_ticker_manager",
        "sector_recommendations",
        "updated_at",  # metadata
    }

    safe_feature_fields = {"enabled", "max_output_tokens"}
    safe_budget_fields = {"global_max_output_tokens"}

    # Check root level fields
    for key in ai_copilot.keys():
        if key not in safe_root_fields:
            errors.append(f"Unsafe field in ai_copilot: {key}")

    # Check unsafe fields are not present
    if "influence_decisions" in ai_copilot:
        errors.append("Cannot modify influence_decisions via UI")

    # Validate types
    if "enabled" in ai_copilot and not isinstance(ai_copilot["enabled"], bool):
        errors.append("ai_copilot.enabled must be boolean")

    if "dry_run" in ai_copilot and not isinstance(ai_copilot["dry_run"], bool):
        errors.append("ai_copilot.dry_run must be boolean")

    if "max_calls_per_run" in ai_copilot:
        if (
            not isinstance(ai_copilot["max_calls_per_run"], int)
            or ai_copilot["max_calls_per_run"] < 0
        ):
            errors.append("ai_copilot.max_calls_per_run must be positive integer")

    # Validate budgets section
    if "budgets" in ai_copilot:
        budgets = ai_copilot["budgets"]
        if not isinstance(budgets, dict):
            errors.append("ai_copilot.budgets must be a dict")
        else:
            for key in budgets.keys():
                if key not in safe_budget_fields:
                    errors.append(f"Unsafe field in budgets: {key}")

            if "global_max_output_tokens" in budgets:
                val = budgets["global_max_output_tokens"]
                if not isinstance(val, int) or val < 0:
                    errors.append("global_max_output_tokens must be positive integer")

    # Validate feature sections
    for feature_name in [
        "trade_rationale",
        "daily_journal",
        "strategy_critique",
        "universe_ticker_manager",
        "sector_recommendations",
    ]:
        if feature_name in ai_copilot:
            feature = ai_copilot[feature_name]
            if not isinstance(feature, dict):
                errors.append(f"ai_copilot.{feature_name} must be a dict")
                continue

            for key in feature.keys():
                if key not in safe_feature_fields:
                    errors.append(f"Unsafe field in {feature_name}: {key}")

            if "enabled" in feature and not isinstance(feature["enabled"], bool):
                errors.append(f"{feature_name}.enabled must be boolean")

            if "max_output_tokens" in feature:
                val = feature["max_output_tokens"]
                if not isinstance(val, int) or val < 0:
                    errors.append(f"{feature_name}.max_output_tokens must be positive integer")

    return len(errors) == 0, errors


def get_config_source(
    field_name: str,
    trading_disabled: bool,
    env_value: Any,
    ui_value: Any,
    yaml_value: Any,
    default_value: Any,
) -> tuple[Any, str]:
    """
    Get effective config value and its source based on precedence.

    Precedence (highest to lowest):
    1. trading_disabled (for enabled-related fields)
    2. Environment variables
    3. UI runtime overrides
    4. YAML config
    5. Defaults

    Args:
        field_name: Name of config field
        trading_disabled: Whether trading is disabled
        env_value: Value from environment variable (None if not set)
        ui_value: Value from UI overrides (None if not set)
        yaml_value: Value from YAML config (None if not set)
        default_value: Default value

    Returns:
        Tuple of (effective_value, source_name)
    """
    # Special handling for enabled field when trading disabled
    if field_name == "enabled" and trading_disabled:
        return False, "trading_disabled"

    # Precedence chain
    if env_value is not None:
        return env_value, "env"
    if ui_value is not None:
        return ui_value, "ui"
    if yaml_value is not None:
        return yaml_value, "yaml"
    return default_value, "default"


def is_sector_recommendations_enabled(config: Any = None) -> bool:
    """
    Check if AI Co-Pilot sector recommendations feature is enabled.

    Checks config flag with proper precedence:
    - If trading disabled → False
    - Otherwise uses config.ai_copilot_sector_recommendations_enabled

    Args:
        config: Config object (loads if None)

    Returns:
        True if sector recommendations are enabled, False otherwise

    Safety:
        - Always returns False if config unavailable
        - Never raises exceptions
    """
    try:
        # Check trading disabled first
        if is_trading_disabled():
            return False

        # Load config if not provided
        if config is None:
            from src.app.config import load_config_with_yaml

            config = load_config_with_yaml()

        # Check master AI Copilot switch
        if not config.ai_copilot_enabled:
            return False

        # Check sector recommendations flag
        return config.ai_copilot_sector_recommendations_enabled

    except Exception as e:
        logger.warning(f"Error checking sector recommendations enabled: {e}")
        return False
