"""Tests for selector runtime overrides."""

from pathlib import Path

import pytest

from src.app.selector_overrides import (
    apply_overrides_to_selector_config,
    get_aggressive_selector_overrides,
    get_normal_selector_overrides,
    load_selector_config_with_overrides,
    load_selector_overrides,
    save_selector_overrides,
)


def test_get_normal_selector_overrides():
    """Test normal mode selector overrides."""
    overrides = get_normal_selector_overrides()

    assert overrides["defaults"]["min_confidence"] == 0.65
    assert overrides["defaults"]["ttl_minutes_buy"] == 180
    assert overrides["candidates_max_count"] == 40
    assert overrides["screening"]["duplicate_suppression_minutes"] == 30


def test_get_aggressive_selector_overrides():
    """Test aggressive mode selector overrides."""
    overrides = get_aggressive_selector_overrides()

    # More aggressive settings
    assert overrides["defaults"]["min_confidence"] < 0.60
    assert overrides["defaults"]["ttl_minutes_buy"] < 180  # Shorter for daytrade
    assert overrides["candidates_max_count"] > 40  # More candidates
    assert overrides["screening"]["duplicate_suppression_minutes"] < 30  # Faster re-eval


def test_save_and_load_selector_overrides(tmp_path, monkeypatch):
    """Test saving and loading selector overrides."""
    monkeypatch.chdir(tmp_path)

    # Save overrides
    overrides = {
        "candidates_max_count": 100,
        "candidates_min_confidence": 0.50,
    }

    success = save_selector_overrides("test_profile", overrides)
    assert success

    # Verify file exists
    assert Path("data/selector_overrides.json").exists()

    # Load back
    loaded = load_selector_overrides()
    assert loaded["profile"] == "test_profile"
    assert loaded["overrides"]["candidates_max_count"] == 100


def test_apply_deep_merge():
    """Test deep merge of nested overrides."""
    base = {
        "level1": {
            "level2a": {"value": 1, "keep": "yes"},
            "level2b": 100,
        },
        "top_level": "original",
    }

    overrides = {
        "level1": {"level2a": {"value": 999}},  # Override nested value
        "top_level": "updated",  # Override top-level
        "new_key": "new_value",  # Add new
    }

    result = apply_overrides_to_selector_config(base, overrides)

    # Check merged values
    assert result["level1"]["level2a"]["value"] == 999  # Overridden
    assert result["level1"]["level2a"]["keep"] == "yes"  # Preserved
    assert result["level1"]["level2b"] == 100  # Preserved
    assert result["top_level"] == "updated"  # Overridden
    assert result["new_key"] == "new_value"  # Added


def test_load_selector_config_with_no_overrides():
    """Test loading selector config without overrides file."""
    # Should load base yaml config only
    config = load_selector_config_with_overrides()

    # Check it has expected yaml structure
    assert "defaults" in config or "sectors_enabled" in config


def test_load_selector_config_with_overrides(tmp_path, monkeypatch):
    """Test loading selector config with overrides applied."""
    monkeypatch.chdir(tmp_path)

    # Create minimal yaml config
    import yaml

    yaml_path = Path("config/selector.yaml")
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    base_config = {
        "candidates_max_count": 20,
        "defaults": {"min_confidence": 0.65},
    }

    with open(yaml_path, "w") as f:
        yaml.dump(base_config, f)

    # Save overrides
    overrides = {
        "candidates_max_count": 80,
        "defaults": {"min_confidence": 0.50},
    }

    save_selector_overrides("aggressive", overrides)

    # Load merged config
    config = load_selector_config_with_overrides(yaml_path)

    # Check overrides were applied
    assert config["candidates_max_count"] == 80
    assert config["defaults"]["min_confidence"] == 0.50


def test_empty_overrides_returns_base_config():
    """Test that empty overrides returns base config unchanged."""
    base_config = {"key": "value", "nested": {"inner": 123}}

    result = apply_overrides_to_selector_config(base_config, {})

    assert result == base_config


def test_aggressive_vs_normal_differences():
    """Test that aggressive and normal modes have meaningful differences."""
    normal = get_normal_selector_overrides()
    aggressive = get_aggressive_selector_overrides()

    # Aggressive should have:
    # - Lower confidence threshold
    assert aggressive["defaults"]["min_confidence"] < normal["defaults"]["min_confidence"]

    # - More candidates
    assert aggressive["candidates_max_count"] > normal["candidates_max_count"]

    # - Shorter TTL (faster rotation for daytrade)
    assert aggressive["defaults"]["ttl_minutes_buy"] < normal["defaults"]["ttl_minutes_buy"]

    # - Faster duplicate suppression
    assert (
        aggressive["screening"]["duplicate_suppression_minutes"]
        < normal["screening"]["duplicate_suppression_minutes"]
    )
