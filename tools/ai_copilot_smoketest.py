"""
AI Co-Pilot Smoketest Tool.

Quick verification tool to check AI Co-Pilot configuration without making OpenAI calls.

Usage:
    python -m tools.ai_copilot_smoketest

Checks:
- Trading disabled status
- AI Co-Pilot effective enabled + sources
- Budget limits
- UI override file status
- Output file locations
"""

import os
import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from src.app.config import load_config_with_yaml, load_yaml_config
from src.app.llm_advisors.config_helpers import get_effective_config_with_sources
from src.app.llm_advisors.utils import is_trading_disabled, load_ui_runtime_overrides


def print_header(title: str):
    """Print section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_status(key: str, value: str, color: str = ""):
    """Print status line."""
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "end": "\033[0m",
    }

    if color:
        print(f"  {key:35} {colors.get(color, '')}{value}{colors['end']}")
    else:
        print(f"  {key:35} {value}")


def main():
    """Run smoketest."""
    print("\n🔍 AI Co-Pilot Smoketest")
    print("="*60)

    # 1. Trading Disabled Status
    print_header("Trading Status")
    trading_disabled = is_trading_disabled()

    if trading_disabled:
        print_status("Trading Disabled", "YES (AI Co-Pilot FORCED OFF)", "red")
        pause_file = Path("state/pause_trading.flag")
        if pause_file.exists():
            try:
                with open(pause_file) as f:
                    timestamp = f.read().strip()
                print_status("  Paused Since", timestamp, "yellow")
            except Exception:
                pass
    else:
        print_status("Trading Disabled", "NO (trading enabled)", "green")

    # 2. Load Config
    print_header("Configuration Loading")

    try:
        config = load_config_with_yaml()
        yaml_config = load_yaml_config()
        print_status("Config Load", "SUCCESS", "green")
    except Exception as e:
        print_status("Config Load", f"FAILED: {e}", "red")
        return 1

    # 3. Effective Config with Sources
    print_header("AI Co-Pilot Effective Config")

    effective_data = get_effective_config_with_sources(config, yaml_config)
    effective = effective_data["effective"]
    sources = effective_data["sources"]

    # Master enabled
    enabled = effective["enabled"]
    enabled_source = sources["enabled"]
    if trading_disabled:
        print_status("Enabled (Effective)", f"FALSE (forced by trading_disabled)", "red")
    elif enabled:
        print_status("Enabled (Effective)", f"TRUE (source: {enabled_source})", "green")
    else:
        print_status("Enabled (Effective)", f"FALSE (source: {enabled_source})", "yellow")

    # Forced reason
    if effective_data.get("forced_reason"):
        print_status("  Forced Reason", effective_data["forced_reason"], "yellow")

    # Other settings
    print_status("Influence Decisions", f"{effective['influence_decisions']} (source: {sources['influence_decisions']})")
    print_status("Model", f"{effective['model']}")
    print_status("Dry Run", f"{effective['dry_run']} (source: {sources['dry_run']})")

    # 4. Budget Limits
    print_header("Budget Limits")

    print_status("Max Calls Per Run", f"{effective['max_calls_per_run']} (source: {sources['max_calls_per_run']})")
    print_status("Global Max Output Tokens", f"{effective['budgets']['global_max_output_tokens']} (source: {sources['budgets']['global_max_output_tokens']})")
    print_status("Timeout", f"{effective['timeout_s']}s")

    # 5. Features
    print_header("Features")

    for feature_name in ["trade_rationale", "daily_journal", "strategy_critique"]:
        feature = effective[feature_name]
        feature_sources = sources[feature_name]

        enabled_str = "ENABLED" if feature["enabled"] else "disabled"
        color = "green" if feature["enabled"] else "yellow"

        print_status(
            f"{feature_name.replace('_', ' ').title()}",
            f"{enabled_str} (source: {feature_sources['enabled']})",
            color
        )
        print_status(
            f"  Max Tokens",
            f"{feature['max_output_tokens']} (source: {feature_sources['max_output_tokens']})"
        )

    # 6. UI Runtime Overrides
    print_header("UI Runtime Overrides")

    overrides_path = Path("data/ui_runtime_overrides.json")
    if overrides_path.exists():
        print_status("Override File", str(overrides_path), "green")
        print_status("  Exists", "YES", "green")

        # Check writable
        try:
            test_write = overrides_path.parent / ".write_test"
            test_write.touch()
            test_write.unlink()
            print_status("  Writable", "YES", "green")
        except Exception:
            print_status("  Writable", "NO", "red")

        # Load overrides
        try:
            overrides = load_ui_runtime_overrides()
            if overrides:
                print_status("  Valid JSON", "YES", "green")
                if "ai_copilot" in overrides:
                    print_status("  Has ai_copilot", "YES", "green")
                else:
                    print_status("  Has ai_copilot", "NO", "yellow")
            else:
                print_status("  Valid JSON", "EMPTY", "yellow")
        except Exception as e:
            print_status("  Valid JSON", f"ERROR: {e}", "red")
    else:
        print_status("Override File", "DOES NOT EXIST (will be created on first write)", "yellow")
        print_status("  Location", str(overrides_path))

        # Check if directory is writable
        try:
            overrides_path.parent.mkdir(parents=True, exist_ok=True)
            test_write = overrides_path.parent / ".write_test"
            test_write.touch()
            test_write.unlink()
            print_status("  Directory Writable", "YES", "green")
        except Exception as e:
            print_status("  Directory Writable", f"NO: {e}", "red")

    # 7. Output File Locations
    print_header("Output File Locations")

    print_status("Status Snapshot", "logs/ai_copilot/latest_status.json")

    status_path = Path("logs/ai_copilot/latest_status.json")
    if status_path.exists():
        print_status("  Exists", "YES", "green")
    else:
        print_status("  Exists", "NO (will be created on first run)", "yellow")

    print_status("Daily Journal", "logs/journal/YYYY-MM-DD.md")
    print_status("Strategy Critique", "data/strategy_memory.jsonl")

    # 8. Environment Variables
    print_header("Environment Variables")

    env_vars = {
        "AI_COPILOT_ENABLED": os.getenv("AI_COPILOT_ENABLED"),
        "AI_COPILOT_DRY_RUN": os.getenv("AI_COPILOT_DRY_RUN"),
        "OPENAI_API_KEY": "***" if os.getenv("OPENAI_API_KEY") else None,
    }

    for var, value in env_vars.items():
        if value:
            print_status(var, value, "blue")
        else:
            print_status(var, "(not set)")

    # 9. Summary
    print_header("Summary")

    if trading_disabled:
        print_status("Status", "⛔ Trading is DISABLED - AI Co-Pilot FORCED OFF", "red")
    elif effective["enabled"]:
        print_status("Status", "✅ AI Co-Pilot is ENABLED and ready", "green")
    else:
        print_status("Status", "⚠️  AI Co-Pilot is DISABLED (but can be enabled)", "yellow")

    print("\n✅ Smoketest Complete")
    print("="*60)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
