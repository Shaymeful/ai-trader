"""
Config helpers for AI Co-Pilot effective configuration with source tracking.

Implements precedence logic: trading_disabled > env > UI > YAML > defaults
"""

import os
from typing import Any

from src.app.config import Config
from src.app.llm_advisors.utils import is_trading_disabled, load_ui_runtime_overrides


def get_effective_config_with_sources(config: Config, yaml_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Get effective AI Co-Pilot configuration with source tracking.

    Args:
        config: Loaded Config object (already has effective values applied)
        yaml_config: Optional YAML config dict for source tracking

    Returns:
        Dict with "effective" and "sources" keys showing values and their origins

    Sources:
        - "trading_disabled": Trading is paused (forces enabled=false)
        - "env": Environment variable
        - "ui": UI runtime override
        - "yaml": YAML config file
        - "default": Default value

    Precedence: trading_disabled > env > ui > yaml > default
    """
    trading_disabled = is_trading_disabled()
    ui_overrides = load_ui_runtime_overrides()
    ui_copilot = ui_overrides.get("ai_copilot", {})

    yaml_copilot = {}
    if yaml_config and "ai_copilot" in yaml_config:
        yaml_copilot = yaml_config["ai_copilot"]

    # Helper to determine source
    def get_source(field_name: str, env_var: str | None = None) -> str:
        """Determine source of a config value."""
        # Special handling for enabled field
        if field_name == "enabled" and trading_disabled:
            return "trading_disabled"

        # Check env
        if env_var and os.getenv(env_var) is not None:
            return "env"

        # Check UI override (handle nested paths)
        if "." in field_name:
            parts = field_name.split(".")
            ui_val = ui_copilot
            try:
                for part in parts:
                    ui_val = ui_val[part]
                if ui_val is not None:
                    return "ui"
            except (KeyError, TypeError):
                pass
        elif field_name in ui_copilot:
            return "ui"

        # Check YAML (handle nested paths)
        if "." in field_name:
            parts = field_name.split(".")
            yaml_val = yaml_copilot
            try:
                for part in parts:
                    yaml_val = yaml_val[part]
                if yaml_val is not None:
                    return "yaml"
            except (KeyError, TypeError):
                pass
        elif field_name in yaml_copilot:
            return "yaml"

        return "default"

    # Build effective config and sources
    effective = {
        "trading_disabled_effective": trading_disabled,
        "enabled": config.ai_copilot_enabled,
        "influence_decisions": config.ai_copilot_influence_decisions,
        "model": config.ai_copilot_model,
        "max_calls_per_run": config.ai_copilot_max_calls_per_run,
        "timeout_s": config.ai_copilot_timeout_s,
        "dry_run": config.ai_copilot_dry_run,
        "budgets": {
            "global_max_output_tokens": config.ai_copilot_global_max_output_tokens,
        },
        "trade_rationale": {
            "enabled": config.ai_copilot_trade_rationale_enabled,
            "max_output_tokens": config.ai_copilot_trade_rationale_max_tokens,
        },
        "daily_journal": {
            "enabled": config.ai_copilot_daily_journal_enabled,
            "max_output_tokens": config.ai_copilot_daily_journal_max_tokens,
        },
        "strategy_critique": {
            "enabled": config.ai_copilot_strategy_critique_enabled,
            "max_output_tokens": config.ai_copilot_strategy_critique_max_tokens,
        },
    }

    sources = {
        "trading_disabled_effective": "runtime",
        "enabled": get_source("enabled", "AI_COPILOT_ENABLED"),
        "influence_decisions": "yaml",  # Cannot be overridden
        "model": "yaml",  # Cannot be overridden
        "max_calls_per_run": get_source("max_calls_per_run"),
        "timeout_s": "yaml",  # Cannot be overridden
        "dry_run": get_source("dry_run", "AI_COPILOT_DRY_RUN"),
        "budgets": {
            "global_max_output_tokens": get_source("budgets.global_max_output_tokens"),
        },
        "trade_rationale": {
            "enabled": get_source("trade_rationale.enabled"),
            "max_output_tokens": get_source("trade_rationale.max_output_tokens"),
        },
        "daily_journal": {
            "enabled": get_source("daily_journal.enabled"),
            "max_output_tokens": get_source("daily_journal.max_output_tokens"),
        },
        "strategy_critique": {
            "enabled": get_source("strategy_critique.enabled"),
            "max_output_tokens": get_source("strategy_critique.max_output_tokens"),
        },
    }

    # Add forced_reason if trading disabled
    forced_reason = None
    if trading_disabled:
        forced_reason = "forced_off_by_trading_disable"

    return {
        "effective": effective,
        "sources": sources,
        "forced_reason": forced_reason,
        "trading_disabled_effective": trading_disabled,
    }
