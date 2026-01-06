"""Tests for universe resolution module."""

from src.app.universe import (
    SectorConfig,
    load_universe_config,
    resolve_universe,
)


def test_resolve_universe_legacy_format():
    """Test resolution with legacy core.symbols format."""
    config_dict = {"universe": {"core": {"symbols": ["SPY", "QQQ", "AAPL"]}}}

    resolution = resolve_universe(config_dict)

    assert resolution.source == "legacy"
    assert resolution.symbols == ["SPY", "QQQ", "AAPL"]
    assert len(resolution.warnings) == 1
    assert "legacy" in resolution.warnings[0].lower()
    assert resolution.deduplication_count == 0
    assert resolution.sectors_used == []


def test_resolve_universe_new_sector_format():
    """Test resolution with new sector format."""
    config_dict = {
        "universe": {
            "sectors": {
                "core_index": {"enabled": True, "symbols": ["SPY", "QQQ"]},
                "mega_cap_tech": {
                    "enabled": True,
                    "symbols": ["AAPL", "MSFT", "NVDA"],
                },
            }
        }
    }

    resolution = resolve_universe(config_dict)

    assert resolution.source == "sectors"
    assert resolution.symbols == ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]
    assert resolution.sectors_used == ["core_index", "mega_cap_tech"]
    assert resolution.deduplication_count == 0


def test_resolve_universe_disabled_sector():
    """Test that disabled sectors are excluded."""
    config_dict = {
        "universe": {
            "sectors": {
                "core_index": {"enabled": True, "symbols": ["SPY", "QQQ"]},
                "disabled_sector": {"enabled": False, "symbols": ["EXCLUDED"]},
            }
        }
    }

    resolution = resolve_universe(config_dict)

    assert "EXCLUDED" not in resolution.symbols
    assert "disabled_sector" not in resolution.sectors_used
    assert "core_index" in resolution.sectors_used


def test_resolve_universe_deduplication():
    """Test deduplication of symbols across sectors."""
    config_dict = {
        "universe": {
            "sectors": {
                "sector_a": {
                    "enabled": True,
                    "symbols": ["SPY", "AAPL", "MSFT"],
                },
                "sector_b": {
                    "enabled": True,
                    "symbols": ["AAPL", "GOOGL", "SPY"],  # Duplicates
                },
            }
        }
    }

    resolution = resolve_universe(config_dict)

    # Should preserve first occurrence order
    assert resolution.symbols == ["SPY", "AAPL", "MSFT", "GOOGL"]
    assert resolution.deduplication_count == 2  # SPY and AAPL duplicated
    assert len(resolution.warnings) == 1
    assert "duplicate" in resolution.warnings[0].lower()


def test_resolve_universe_alphabetical_fallback():
    """Test alphabetical fallback mode."""
    config_dict = {
        "universe": {
            "fallback_mode": "alphabetical",
            "sectors": {"sector_a": {"enabled": True, "symbols": ["ZZZ", "AAA", "MMM"]}},
        }
    }

    resolution = resolve_universe(config_dict)

    assert resolution.symbols == ["AAA", "MMM", "ZZZ"]


def test_resolve_universe_preserve_order():
    """Test preserve_order fallback mode (default)."""
    config_dict = {
        "universe": {
            "fallback_mode": "preserve_order",
            "sectors": {"sector_a": {"enabled": True, "symbols": ["ZZZ", "AAA", "MMM"]}},
        }
    }

    resolution = resolve_universe(config_dict)

    # Should maintain declaration order
    assert resolution.symbols == ["ZZZ", "AAA", "MMM"]


def test_resolve_universe_empty():
    """Test resolution with no universe config."""
    config_dict = {}

    resolution = resolve_universe(config_dict)

    assert resolution.source == "empty"
    assert resolution.symbols == []
    assert len(resolution.warnings) == 1
    assert "no universe configuration" in resolution.warnings[0].lower()


def test_resolve_universe_empty_sectors():
    """Test resolution with empty sectors dict."""
    config_dict = {"universe": {"sectors": {}}}

    resolution = resolve_universe(config_dict)

    assert resolution.source == "empty"
    assert resolution.symbols == []


def test_load_universe_config_legacy():
    """Test loading legacy universe config."""
    config_dict = {"universe": {"core": {"symbols": ["SPY", "QQQ"]}}}

    universe_config = load_universe_config(config_dict)

    assert universe_config.legacy_symbols == ["SPY", "QQQ"]
    assert len(universe_config.sectors) == 0
    assert universe_config.fallback_mode == "preserve_order"


def test_load_universe_config_sectors():
    """Test loading sector-based universe config."""
    config_dict = {
        "universe": {
            "fallback_mode": "alphabetical",
            "sectors": {
                "core_index": {
                    "enabled": True,
                    "description": "Index ETFs",
                    "symbols": ["SPY", "QQQ"],
                }
            },
        }
    }

    universe_config = load_universe_config(config_dict)

    assert universe_config.legacy_symbols is None
    assert len(universe_config.sectors) == 1
    assert "core_index" in universe_config.sectors
    assert universe_config.sectors["core_index"].description == "Index ETFs"
    assert universe_config.sectors["core_index"].enabled is True
    assert universe_config.fallback_mode == "alphabetical"


def test_sector_config_defaults():
    """Test SectorConfig default values."""
    sector = SectorConfig(name="test", symbols=["SPY"])

    assert sector.enabled is True
    assert sector.description == ""


def test_backward_compatibility_exact_match():
    """Test that new format with default config matches old format exactly."""
    # Old format
    old_config = {
        "universe": {
            "core": {
                "symbols": [
                    "SPY",
                    "QQQ",
                    "AAPL",
                    "MSFT",
                    "NVDA",
                    "AMD",
                    "META",
                    "GOOGL",
                    "TSLA",
                    "XLF",
                    "XLE",
                    "XLV",
                ]
            }
        }
    }

    # New format (default sectors all enabled)
    new_config = {
        "universe": {
            "fallback_mode": "preserve_order",
            "sectors": {
                "core_index": {"enabled": True, "symbols": ["SPY", "QQQ"]},
                "mega_cap_tech": {
                    "enabled": True,
                    "symbols": [
                        "AAPL",
                        "MSFT",
                        "NVDA",
                        "AMD",
                        "META",
                        "GOOGL",
                        "TSLA",
                    ],
                },
                "us_sector_etfs": {"enabled": True, "symbols": ["XLF", "XLE", "XLV"]},
            },
        }
    }

    old_resolution = resolve_universe(old_config)
    new_resolution = resolve_universe(new_config)

    # Symbols should match exactly
    assert old_resolution.symbols == new_resolution.symbols
    # Both should have 12 symbols
    assert len(old_resolution.symbols) == 12
    assert len(new_resolution.symbols) == 12


def test_resolve_universe_default_enabled():
    """Test that sectors without enabled field default to True."""
    config_dict = {
        "universe": {
            "sectors": {
                "sector_a": {
                    "symbols": ["SPY", "QQQ"]
                    # Note: no "enabled" field
                }
            }
        }
    }

    resolution = resolve_universe(config_dict)

    # Should include symbols since default is enabled=True
    assert resolution.symbols == ["SPY", "QQQ"]
    assert "sector_a" in resolution.sectors_used


def test_resolve_universe_multiple_disabled_sectors():
    """Test multiple disabled sectors don't affect enabled ones."""
    config_dict = {
        "universe": {
            "sectors": {
                "enabled_sector": {"enabled": True, "symbols": ["SPY"]},
                "disabled_1": {"enabled": False, "symbols": ["EXCLUDED1"]},
                "disabled_2": {"enabled": False, "symbols": ["EXCLUDED2"]},
                "enabled_sector_2": {"enabled": True, "symbols": ["QQQ"]},
            }
        }
    }

    resolution = resolve_universe(config_dict)

    assert resolution.symbols == ["SPY", "QQQ"]
    assert len(resolution.sectors_used) == 2
    assert "enabled_sector" in resolution.sectors_used
    assert "enabled_sector_2" in resolution.sectors_used
