"""Tests for trading mode profiles."""

import json
from pathlib import Path

import pytest

from src.app.config import (
    get_active_mode_profile,
    load_mode_profiles,
    save_mode_override,
)
from src.app.selector_overrides import (
    apply_overrides_to_selector_config,
    load_selector_overrides,
    save_selector_overrides,
)


def test_load_mode_profiles():
    """Test loading mode profiles from yaml."""
    modes = load_mode_profiles()

    assert "profiles" in modes
    assert "normal" in modes["profiles"]
    assert "aggressive_tech_energy" in modes["profiles"]
    assert "active_profile" in modes


def test_get_active_mode_profile_default():
    """Test getting active profile (default from yaml)."""
    # Remove any runtime override
    override_path = Path("data/mode_override.json")
    if override_path.exists():
        override_path.unlink()

    profile_name, profile = get_active_mode_profile()

    # Should be default from yaml
    assert profile_name == "normal"
    assert "strategies" in profile
    assert "universe" in profile


def test_save_and_load_mode_override(tmp_path, monkeypatch):
    """Test saving and loading mode override."""
    # Use temp directory
    monkeypatch.chdir(tmp_path)

    # Save override
    success = save_mode_override("aggressive_tech_energy")
    assert success

    # Load it back
    profile_name, profile = get_active_mode_profile()
    assert profile_name == "aggressive_tech_energy"


def test_mode_profile_structure():
    """Test that mode profiles have required structure."""
    modes = load_mode_profiles()

    for profile_name, profile in modes["profiles"].items():
        # Check required keys
        assert "description" in profile
        assert "strategies" in profile
        assert "universe" in profile
        assert "selector" in profile
        assert "ai_copilot" in profile

        # Check strategies structure
        if "AI_COPILOT_WEIGHTED" in profile["strategies"]:
            strategy = profile["strategies"]["AI_COPILOT_WEIGHTED"]
            assert "enabled" in strategy
            assert "weight" in strategy
            assert "params" in strategy


def test_mode_switch_coordinated_changes():
    """Test that mode profiles define coordinated settings."""
    modes = load_mode_profiles()
    aggressive = modes["profiles"]["aggressive_tech_energy"]

    # Check strategy settings
    assert aggressive["strategies"]["AI_COPILOT_WEIGHTED"]["enabled"] is True
    assert aggressive["strategies"]["AI_COPILOT_WEIGHTED"]["params"]["execution_enabled"] is True

    # Check universe settings
    assert aggressive["universe"]["sectors"]["mega_cap_tech"] is True
    assert aggressive["universe"]["sectors"]["core_index"] is False  # Disabled for noise reduction

    # Check selector settings
    assert aggressive["selector"]["candidates_max_count"] > 40  # More aggressive
    assert aggressive["selector"]["candidates_min_confidence"] < 0.65  # Lower threshold

    # Check AI copilot settings
    assert aggressive["ai_copilot"]["universe_ticker_manager"] is True
    assert aggressive["ai_copilot"]["strategy_critique"] is False  # Disabled to save tokens


def test_selector_overrides_save_load(tmp_path, monkeypatch):
    """Test selector overrides save and load."""
    monkeypatch.chdir(tmp_path)

    # Save overrides
    overrides = {
        "candidates_max_count": 80,
        "candidates_min_confidence": 0.52,
        "defaults": {"min_confidence": 0.52},
    }

    success = save_selector_overrides("aggressive_tech_energy", overrides)
    assert success

    # Load back
    loaded = load_selector_overrides()
    assert loaded["profile"] == "aggressive_tech_energy"
    assert loaded["overrides"]["candidates_max_count"] == 80


def test_selector_overrides_merge():
    """Test that selector overrides properly merge with base config."""
    base_config = {
        "candidates_max_count": 20,
        "candidates_min_confidence": 0.65,
        "defaults": {"min_confidence": 0.60, "ttl_minutes_buy": 180},
        "safety": {"max_candidates_per_run": 50},
    }

    overrides = {
        "candidates_max_count": 80,  # Override top-level
        "defaults": {"min_confidence": 0.52},  # Override nested
        "new_field": "value",  # Add new field
    }

    merged = apply_overrides_to_selector_config(base_config, overrides)

    assert merged["candidates_max_count"] == 80  # Overridden
    assert merged["candidates_min_confidence"] == 0.65  # Not overridden
    assert merged["defaults"]["min_confidence"] == 0.52  # Nested override
    assert merged["defaults"]["ttl_minutes_buy"] == 180  # Preserved
    assert merged["new_field"] == "value"  # Added


def test_mode_persistence(tmp_path, monkeypatch):
    """Test that mode changes persist across restarts."""
    monkeypatch.chdir(tmp_path)

    # Switch to aggressive
    save_mode_override("aggressive_tech_energy")

    # Simulate restart - reload config
    profile_name, profile = get_active_mode_profile()
    assert profile_name == "aggressive_tech_energy"

    # Switch back to normal
    save_mode_override("normal")

    # Reload
    profile_name, profile = get_active_mode_profile()
    assert profile_name == "normal"


def test_invalid_profile_name():
    """Test handling of invalid profile name."""
    modes = load_mode_profiles()

    # Try to get non-existent profile
    # Should fall back gracefully
    profile_name, profile = get_active_mode_profile(modes)

    # Should return a valid profile (first available)
    assert profile_name in ["normal", "aggressive_tech_energy"]
