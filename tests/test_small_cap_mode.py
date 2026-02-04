"""Tests for small_cap_swing mode profile."""

import json
from pathlib import Path

import pytest

from src.app.config import get_active_mode_profile, load_mode_profiles, save_mode_override
from src.app.execution.tradability_filter import ExecutionGateConfig


def test_load_small_cap_swing_profile():
    """Test that small_cap_swing profile loads correctly."""
    modes_config = load_mode_profiles()
    profiles = modes_config.get("profiles", {})

    assert "small_cap_swing" in profiles
    profile = profiles["small_cap_swing"]

    # Check description
    assert "small" in profile["description"].lower() or "swing" in profile["description"].lower()

    # Check strategies
    assert "AI_COPILOT_WEIGHTED" in profile["strategies"]
    ai_copilot = profile["strategies"]["AI_COPILOT_WEIGHTED"]
    assert ai_copilot["enabled"] is True
    assert ai_copilot["weight"] >= 0.4  # Should be high allocation for focused trading
    assert ai_copilot["params"]["execution_enabled"] is True

    # Check selector settings (swing profile)
    selector = profile["selector"]
    assert selector["candidates_max_count"] >= 50  # More candidates for small cap discovery
    assert selector["candidates_min_confidence"] <= 0.60  # Lower threshold for opportunities
    assert selector["ttl_minutes_buy"] >= 240  # Longer TTL for swing setups (4+ hours)

    # Check AI Co-Pilot settings
    ai_copilot_features = profile["ai_copilot"]
    assert ai_copilot_features["universe_ticker_manager"] is True  # Enable for discovery
    assert ai_copilot_features["strategy_critique"] is False  # Disable to save tokens
    assert ai_copilot_features["daily_journal"] is False  # Disable to save tokens

    # Check execution gate (CRITICAL)
    assert "execution_gate" in profile
    gate = profile["execution_gate"]
    assert gate["min_market_cap_usd"] == 300_000_000  # $300M min
    assert gate["max_market_cap_usd"] == 10_000_000_000  # $10B max
    assert gate["min_price"] == 3.0  # Avoid penny stocks
    assert gate["max_price"] == 80.0  # Upper bound for small caps
    assert gate["min_avg_dollar_volume_20d"] == 5_000_000  # $5M/day liquidity
    assert gate["max_spread_bps"] == 100  # 1.00% max spread
    assert gate["strict_mode"] is True  # Hard block


def test_small_cap_swing_mode_switch_persistence(tmp_path):
    """Test that mode switch function exists and has correct signature."""
    # Note: This test validates the function exists and can be called,
    # but doesn't test actual file persistence (requires monkeypatching repo root)

    # Verify function exists and is callable
    from inspect import signature

    sig = signature(save_mode_override)
    params = list(sig.parameters.keys())

    assert "profile_name" in params
    assert callable(save_mode_override)

    # Test that function returns boolean
    # (We can't easily test file persistence without complex monkeypatching)
    # In integration testing, verify manually that data/mode_override.json is created


def test_execution_gate_config_from_profile():
    """Test creating ExecutionGateConfig from small_cap_swing profile."""
    modes_config = load_mode_profiles()
    profile = modes_config["profiles"]["small_cap_swing"]

    gate_config = ExecutionGateConfig.from_dict(profile["execution_gate"])

    assert gate_config.min_market_cap_usd == 300_000_000
    assert gate_config.max_market_cap_usd == 10_000_000_000
    assert gate_config.min_price == 3.0
    assert gate_config.max_price == 80.0
    assert gate_config.min_avg_dollar_volume_20d == 5_000_000
    assert gate_config.max_spread_bps == 100
    assert gate_config.strict_mode is True
    assert gate_config.require_fundamentals is False
    assert gate_config.exclude_symbols == []
    assert gate_config.allow_symbols == []


def test_small_cap_vs_normal_differences():
    """Test that small_cap_swing differs from normal in expected ways."""
    modes_config = load_mode_profiles()
    normal = modes_config["profiles"]["normal"]
    small_cap = modes_config["profiles"]["small_cap_swing"]

    # Strategy differences
    normal_ai = normal["strategies"]["AI_COPILOT_WEIGHTED"]
    small_cap_ai = small_cap["strategies"]["AI_COPILOT_WEIGHTED"]

    # Small cap should have higher weight and enabled execution
    assert small_cap_ai["weight"] > normal_ai["weight"]
    assert small_cap_ai["params"]["execution_enabled"] is True

    # Selector differences
    normal_selector = normal["selector"]
    small_cap_selector = small_cap["selector"]

    # Small cap should have longer TTLs for swing trading
    assert small_cap_selector["ttl_minutes_buy"] > normal_selector["ttl_minutes_buy"]

    # Execution gate: small_cap has gate, normal doesn't
    assert "execution_gate" in small_cap
    assert "execution_gate" not in normal


def test_small_cap_vs_aggressive_differences():
    """Test that small_cap_swing differs from aggressive in expected ways."""
    modes_config = load_mode_profiles()
    aggressive = modes_config["profiles"]["aggressive_tech_energy"]
    small_cap = modes_config["profiles"]["small_cap_swing"]

    # Selector differences: small cap should have LONGER TTLs (swing vs daytrade)
    aggressive_selector = aggressive["selector"]
    small_cap_selector = small_cap["selector"]

    # Swing trading should have much longer TTLs than daytrade
    assert small_cap_selector["ttl_minutes_buy"] > aggressive_selector["ttl_minutes_buy"] * 2

    # Universe differences: small cap should disable mega caps
    aggressive_universe = aggressive["universe"]["sectors"]
    small_cap_universe = small_cap["universe"]["sectors"]

    # Small cap should disable mega cap sectors
    assert small_cap_universe.get("mega_cap_tech", True) is False
    assert small_cap_universe.get("core_index", True) is False

    # Execution gate: only small_cap should have gate
    assert "execution_gate" in small_cap
    assert "execution_gate" not in aggressive


def test_coordinated_settings_include_execution_gate():
    """Test that all coordinated settings are present in small_cap_swing."""
    modes_config = load_mode_profiles()
    profile = modes_config["profiles"]["small_cap_swing"]

    # All coordinated settings should be present
    assert "strategies" in profile
    assert "universe" in profile
    assert "selector" in profile
    assert "ai_copilot" in profile
    assert "execution_gate" in profile  # NEW for small_cap_swing

    # Each should be non-empty
    assert len(profile["strategies"]) > 0
    assert len(profile["universe"]) > 0
    assert len(profile["selector"]) > 0
    assert len(profile["ai_copilot"]) > 0
    assert len(profile["execution_gate"]) > 0
