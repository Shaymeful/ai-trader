"""Tests for universe registry module."""

import json
import tempfile
from pathlib import Path

import pytest

from src.app.universe_registry import UniverseRegistry


@pytest.fixture
def temp_config_dir():
    """Create temporary directory for config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def base_config_yaml(temp_config_dir):
    """Create a minimal base config.yaml for testing."""
    config_path = temp_config_dir / "config.yaml"
    config_content = """
timeframe: "1h"
universe:
  fallback_mode: "preserve_order"
  sectors:
    core_index:
      enabled: true
      description: "Index ETFs"
      symbols:
        - SPY
        - QQQ
    mega_cap_tech:
      enabled: true
      description: "Tech stocks"
      symbols:
        - AAPL
        - MSFT
        - NVDA
    us_sector_etfs:
      enabled: true
      description: "Sector ETFs"
      symbols:
        - XLF
        - XLE
"""
    config_path.write_text(config_content, encoding="utf-8")
    return config_path


@pytest.fixture
def overrides_path(temp_config_dir):
    """Path for overrides JSON file."""
    return temp_config_dir / "universe_overrides.json"


def test_registry_initialization_no_overrides(base_config_yaml, overrides_path):
    """Test registry initializes correctly without overrides file."""
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    assert len(registry.sectors) == 3
    assert "core_index" in registry.sectors
    assert "mega_cap_tech" in registry.sectors
    assert "us_sector_etfs" in registry.sectors

    # All sectors should be enabled by default
    assert registry.sectors["core_index"].enabled is True
    assert registry.sectors["mega_cap_tech"].enabled is True
    assert registry.sectors["us_sector_etfs"].enabled is True

    # No overrides should exist
    assert len(registry.overrides) == 0


def test_registry_initialization_with_overrides(base_config_yaml, overrides_path):
    """Test registry loads and applies existing overrides."""
    # Create overrides file
    overrides_data = {
        "sectors": {
            "mega_cap_tech": {
                "enabled": False,
                "active_version": 1,
                "pending_version": None,
                "last_modified": "2026-01-06T16:30:00+00:00",
            }
        },
        "registry_version": 1,
        "last_saved": "2026-01-06T16:30:00+00:00",
    }
    overrides_path.write_text(json.dumps(overrides_data, indent=2), encoding="utf-8")

    # Load registry
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    # mega_cap_tech should be disabled
    assert registry.sectors["mega_cap_tech"].enabled is False
    assert "mega_cap_tech" in registry.overrides
    assert registry.overrides["mega_cap_tech"].active_version == 1

    # Other sectors should still be enabled
    assert registry.sectors["core_index"].enabled is True
    assert registry.sectors["us_sector_etfs"].enabled is True


def test_stage_change_creates_override(base_config_yaml, overrides_path):
    """Test that stage_change creates a new override."""
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    # Stage a change
    pending_version = registry.stage_change("mega_cap_tech", False)

    assert pending_version == 1
    assert registry.sectors["mega_cap_tech"].enabled is False
    assert "mega_cap_tech" in registry.overrides

    override = registry.overrides["mega_cap_tech"]
    assert override.enabled is False
    assert override.pending_version == 1
    assert override.last_modified is not None


def test_stage_change_updates_existing_override(base_config_yaml, overrides_path):
    """Test that stage_change updates an existing override."""
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    # First change
    registry.stage_change("mega_cap_tech", False)
    registry.check_and_activate_pending()  # Activate to set active_version

    # Second change
    pending_version = registry.stage_change("mega_cap_tech", True)

    assert pending_version == 2
    assert registry.sectors["mega_cap_tech"].enabled is True
    assert registry.overrides["mega_cap_tech"].pending_version == 2


def test_stage_change_invalid_sector(base_config_yaml, overrides_path):
    """Test that stage_change raises ValueError for invalid sector."""
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    with pytest.raises(ValueError, match="Unknown sector"):
        registry.stage_change("invalid_sector", False)


def test_save_overrides_atomic_write(base_config_yaml, overrides_path):
    """Test that _save_overrides writes atomically."""
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    # Stage a change (triggers save)
    registry.stage_change("mega_cap_tech", False)

    # Verify file exists and is valid JSON
    assert overrides_path.exists()
    data = json.loads(overrides_path.read_text(encoding="utf-8"))

    assert "sectors" in data
    assert "mega_cap_tech" in data["sectors"]
    assert data["sectors"]["mega_cap_tech"]["enabled"] is False
    assert "registry_version" in data
    assert "last_saved" in data


def test_load_overrides_handles_missing_file(base_config_yaml, overrides_path):
    """Test that _load_overrides handles missing file gracefully."""
    # Don't create overrides file
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    # Should load successfully with no overrides
    assert len(registry.overrides) == 0
    assert len(registry.sectors) == 3


def test_check_and_activate_pending(base_config_yaml, overrides_path):
    """Test that check_and_activate_pending promotes versions."""
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    # Stage changes
    registry.stage_change("mega_cap_tech", False)
    registry.stage_change("core_index", False)

    # Activate pending
    activated = registry.check_and_activate_pending()

    assert len(activated) == 2
    assert ("mega_cap_tech", 0, 1) in activated
    assert ("core_index", 0, 1) in activated

    # Pending versions should be cleared
    assert registry.overrides["mega_cap_tech"].pending_version is None
    assert registry.overrides["core_index"].pending_version is None

    # Active versions should be updated
    assert registry.overrides["mega_cap_tech"].active_version == 1
    assert registry.overrides["core_index"].active_version == 1


def test_check_and_activate_pending_no_changes(base_config_yaml, overrides_path):
    """Test that check_and_activate_pending returns empty list when no pending changes."""
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    activated = registry.check_and_activate_pending()

    assert len(activated) == 0


def test_reset_to_defaults(base_config_yaml, overrides_path):
    """Test that reset_to_defaults clears overrides."""
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    # Create some overrides
    registry.stage_change("mega_cap_tech", False)
    registry.stage_change("core_index", False)

    assert overrides_path.exists()
    assert len(registry.overrides) == 2

    # Reset
    registry.reset_to_defaults()

    # Overrides should be cleared
    assert not overrides_path.exists()
    assert len(registry.overrides) == 0

    # All sectors should be enabled (default)
    assert registry.sectors["mega_cap_tech"].enabled is True
    assert registry.sectors["core_index"].enabled is True


def test_resolve_respects_enabled_flags(base_config_yaml, overrides_path):
    """Test that resolve() respects enabled flags."""
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    # All enabled - should have all 7 symbols
    resolution = registry.resolve()
    assert len(resolution.symbols) == 7
    assert "SPY" in resolution.symbols
    assert "AAPL" in resolution.symbols
    assert "XLF" in resolution.symbols

    # Disable mega_cap_tech
    registry.stage_change("mega_cap_tech", False)
    resolution = registry.resolve()

    # Should only have 4 symbols (SPY, QQQ, XLF, XLE)
    assert len(resolution.symbols) == 4
    assert "SPY" in resolution.symbols
    assert "QQQ" in resolution.symbols
    assert "XLF" in resolution.symbols
    assert "XLE" in resolution.symbols

    # Tech symbols should be excluded
    assert "AAPL" not in resolution.symbols
    assert "MSFT" not in resolution.symbols
    assert "NVDA" not in resolution.symbols


def test_resolve_all_disabled(base_config_yaml, overrides_path):
    """Test that resolve() handles all sectors disabled."""
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    # Disable all sectors
    registry.stage_change("core_index", False)
    registry.stage_change("mega_cap_tech", False)
    registry.stage_change("us_sector_etfs", False)

    resolution = registry.resolve()

    # Should return empty symbol list
    assert len(resolution.symbols) == 0
    assert resolution.source == "sectors"


def test_backward_compatibility_no_overrides_file(base_config_yaml, overrides_path):
    """Test that registry works without overrides file (backward compatibility)."""
    # Don't create overrides file
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    # Should resolve all symbols
    resolution = registry.resolve()
    assert len(resolution.symbols) == 7
    assert resolution.source == "sectors"


def test_override_unknown_sector_ignored(base_config_yaml, overrides_path):
    """Test that overrides for unknown sectors are ignored safely."""
    # Create overrides with unknown sector
    overrides_data = {
        "sectors": {
            "unknown_sector": {
                "enabled": False,
                "active_version": 1,
                "pending_version": None,
                "last_modified": "2026-01-06T16:30:00+00:00",
            },
            "mega_cap_tech": {
                "enabled": False,
                "active_version": 1,
                "pending_version": None,
                "last_modified": "2026-01-06T16:30:00+00:00",
            },
        },
        "registry_version": 1,
        "last_saved": "2026-01-06T16:30:00+00:00",
    }
    overrides_path.write_text(json.dumps(overrides_data, indent=2), encoding="utf-8")

    # Load registry
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    # Known sector should have override applied
    assert registry.sectors["mega_cap_tech"].enabled is False

    # Unknown sector should be ignored (no crash)
    assert "unknown_sector" not in registry.sectors
    assert "unknown_sector" not in registry.overrides


def test_multiple_stage_and_activate_cycles(base_config_yaml, overrides_path):
    """Test multiple cycles of staging and activating changes."""
    registry = UniverseRegistry(base_config_path=base_config_yaml, overrides_path=overrides_path)

    # Cycle 1
    registry.stage_change("mega_cap_tech", False)
    activated = registry.check_and_activate_pending()
    assert len(activated) == 1
    assert registry.overrides["mega_cap_tech"].active_version == 1

    # Cycle 2
    registry.stage_change("mega_cap_tech", True)
    activated = registry.check_and_activate_pending()
    assert len(activated) == 1
    assert registry.overrides["mega_cap_tech"].active_version == 2

    # Cycle 3
    registry.stage_change("core_index", False)
    registry.stage_change("mega_cap_tech", False)
    activated = registry.check_and_activate_pending()
    assert len(activated) == 2
    assert registry.overrides["core_index"].active_version == 1
    assert registry.overrides["mega_cap_tech"].active_version == 3
