"""
Selector Runtime Overrides.

Provides mechanism to override selector.yaml settings at runtime based on
trading mode profiles (Normal vs Aggressive).

Pattern: Similar to strategies_overrides.json and ui_runtime_overrides.json
File: data/selector_overrides.json

Usage:
    from src.app.selector_overrides import load_selector_config_with_overrides

    config = load_selector_config_with_overrides()
    # config now has yaml defaults merged with profile overrides
"""

import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("ai-trader.selector_overrides")


def load_selector_yaml(selector_path: Path | None = None) -> dict[str, Any]:
    """
    Load selector.yaml configuration.

    Args:
        selector_path: Path to selector.yaml (defaults to config/selector.yaml)

    Returns:
        Dictionary with selector configuration
    """
    if selector_path is None:
        # Assume we're in repo root or can navigate to it
        repo_root = Path(__file__).resolve().parents[2]
        selector_path = repo_root / "config" / "selector.yaml"

    if not selector_path.exists():
        logger.warning(f"Selector config not found: {selector_path}")
        return {}

    with open(selector_path) as f:
        return yaml.safe_load(f) or {}


def load_selector_overrides() -> dict[str, Any]:
    """
    Load selector runtime overrides from data/selector_overrides.json.

    Returns:
        Dictionary with overrides, or empty dict if file doesn't exist
    """
    overrides_path = Path("data/selector_overrides.json")

    if not overrides_path.exists():
        return {}

    try:
        with open(overrides_path, "r", encoding="utf-8") as f:
            overrides = json.load(f)

        if not isinstance(overrides, dict):
            logger.warning("Selector overrides is not a dict, ignoring")
            return {}

        logger.debug(f"Loaded selector overrides: profile={overrides.get('profile')}")
        return overrides

    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in selector overrides, ignoring: {e}")
        return {}
    except Exception as e:
        logger.warning(f"Error loading selector overrides: {e}")
        return {}


def save_selector_overrides(profile: str, overrides: dict[str, Any]) -> bool:
    """
    Save selector runtime overrides to data/selector_overrides.json.

    Args:
        profile: Mode profile name (e.g., "normal", "aggressive_tech_energy")
        overrides: Dictionary of override values

    Returns:
        True if successful, False otherwise
    """
    overrides_path = Path("data/selector_overrides.json")

    try:
        overrides_path.parent.mkdir(parents=True, exist_ok=True)

        from datetime import UTC, datetime

        data = {
            "profile": profile,
            "overrides": overrides,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        # Atomic write
        temp_path = overrides_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        temp_path.replace(overrides_path)

        logger.info(f"Saved selector overrides for profile: {profile}")
        return True

    except Exception as e:
        logger.error(f"Failed to save selector overrides: {e}")
        return False


def apply_overrides_to_selector_config(
    selector_config: dict[str, Any], overrides: dict[str, Any]
) -> dict[str, Any]:
    """
    Apply runtime overrides to selector configuration.

    Merges overrides into selector_config, updating values at any depth.

    Args:
        selector_config: Base selector configuration from yaml
        overrides: Override values to apply

    Returns:
        Updated configuration dict
    """
    if not overrides:
        return selector_config

    # Deep merge overrides into config
    def deep_merge(base: dict, updates: dict) -> dict:
        """Deep merge updates into base."""
        result = base.copy()
        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    return deep_merge(selector_config, overrides)


def load_selector_config_with_overrides(
    selector_path: Path | None = None,
) -> dict[str, Any]:
    """
    Load selector configuration with runtime overrides applied.

    Process:
    1. Load config/selector.yaml
    2. Load data/selector_overrides.json
    3. Merge overrides into yaml config
    4. Return merged config

    Args:
        selector_path: Optional path to selector.yaml

    Returns:
        Merged configuration dictionary
    """
    # Load base config
    selector_config = load_selector_yaml(selector_path)

    # Load overrides
    overrides_data = load_selector_overrides()
    overrides = overrides_data.get("overrides", {})

    if overrides:
        profile = overrides_data.get("profile", "unknown")
        logger.info(f"Applying selector overrides from profile: {profile}")

        # Apply overrides
        selector_config = apply_overrides_to_selector_config(selector_config, overrides)

    return selector_config


def get_aggressive_selector_overrides() -> dict[str, Any]:
    """
    Get recommended selector overrides for Aggressive mode.

    Returns:
        Dictionary of override values
    """
    return {
        "defaults": {
            "min_confidence": 0.52,  # Lower threshold
            "ttl_minutes_buy": 90,  # Shorter TTL for daytrade
            "ttl_minutes_sell": 60,
            "ttl_minutes_watch": 120,
        },
        "safety": {
            "max_candidates_per_run": 25,  # More candidates per run
        },
        "screening": {
            "duplicate_suppression_minutes": 12,  # Allow faster re-evaluation
        },
        "candidates_min_confidence": 0.52,  # Match defaults.min_confidence
        "candidates_max_count": 80,  # More total candidates
    }


def get_normal_selector_overrides() -> dict[str, Any]:
    """
    Get recommended selector overrides for Normal mode.

    Returns:
        Dictionary of override values (use yaml defaults)
    """
    return {
        "defaults": {
            "min_confidence": 0.65,
            "ttl_minutes_buy": 180,
            "ttl_minutes_sell": 120,
            "ttl_minutes_watch": 240,
        },
        "safety": {
            "max_candidates_per_run": 15,
        },
        "screening": {
            "duplicate_suppression_minutes": 30,
        },
        "candidates_min_confidence": 0.65,
        "candidates_max_count": 40,
    }
