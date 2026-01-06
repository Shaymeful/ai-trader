"""Universe resolution module for sector-based symbol selection."""

import random

from pydantic import BaseModel, Field


class SectorConfig(BaseModel):
    """Sector group configuration."""

    name: str
    symbols: list[str]
    enabled: bool = True
    description: str = ""


class UniverseConfig(BaseModel):
    """Universe configuration with sectors."""

    sectors: dict[str, SectorConfig] = Field(default_factory=dict)
    fallback_mode: str = "preserve_order"
    legacy_symbols: list[str] | None = None


class UniverseResolution(BaseModel):
    """Result of universe resolution."""

    symbols: list[str]
    source: str  # "sectors", "legacy", "empty"
    sectors_used: list[str]
    deduplication_count: int
    warnings: list[str] = Field(default_factory=list)


def resolve_universe(config_dict: dict) -> UniverseResolution:
    """
    Resolve universe from config dictionary.

    Resolution priority:
    1. Check for legacy format (universe.core.symbols) - backward compatibility
    2. Check for new sector format (universe.sectors)
    3. Return empty resolution if neither found

    Deduplication strategy:
    - Collect symbols in declaration order (preserve_order mode)
    - Track first occurrence of each symbol
    - Emit warning if duplicates found

    Args:
        config_dict: Raw YAML config dictionary

    Returns:
        UniverseResolution with deduplicated symbols
    """
    universe_config = config_dict.get("universe", {})

    # BACKWARD COMPATIBILITY: Check for legacy format first
    if "core" in universe_config and "symbols" in universe_config["core"]:
        legacy_symbols = universe_config["core"]["symbols"]
        return UniverseResolution(
            symbols=legacy_symbols,
            source="legacy",
            sectors_used=[],
            deduplication_count=0,
            warnings=["Using legacy core.symbols format (consider migrating to sectors)"],
        )

    # NEW FORMAT: Resolve from sectors
    sectors_config = universe_config.get("sectors", {})
    if not sectors_config:
        return UniverseResolution(
            symbols=[],
            source="empty",
            sectors_used=[],
            deduplication_count=0,
            warnings=["No universe configuration found"],
        )

    # Parse fallback mode
    fallback_mode = universe_config.get("fallback_mode", "preserve_order")

    # Collect symbols from enabled sectors
    seen_symbols = {}  # symbol -> first sector name
    ordered_symbols = []
    sectors_used = []
    duplicate_count = 0

    for sector_name, sector_data in sectors_config.items():
        if not sector_data.get("enabled", True):
            continue

        sectors_used.append(sector_name)
        sector_symbols = sector_data.get("symbols", [])

        for symbol in sector_symbols:
            if symbol in seen_symbols:
                duplicate_count += 1
                # Already seen - skip (preserve first occurrence)
                continue

            seen_symbols[symbol] = sector_name
            ordered_symbols.append(symbol)

    # Apply fallback mode sorting
    if fallback_mode == "alphabetical":
        ordered_symbols.sort()
    elif fallback_mode == "random":
        random.shuffle(ordered_symbols)
    # preserve_order: no change (already in declaration order)

    warnings = []
    if duplicate_count > 0:
        warnings.append(f"Removed {duplicate_count} duplicate symbols across sectors")

    return UniverseResolution(
        symbols=ordered_symbols,
        source="sectors",
        sectors_used=sectors_used,
        deduplication_count=duplicate_count,
        warnings=warnings,
    )


def load_universe_config(config_dict: dict) -> UniverseConfig:
    """
    Load universe configuration from YAML dict.

    Supports both legacy and new sector formats.

    Args:
        config_dict: Raw YAML config dictionary

    Returns:
        UniverseConfig with parsed sectors
    """
    universe_config = config_dict.get("universe", {})

    # Check for legacy format
    if "core" in universe_config and "symbols" in universe_config["core"]:
        return UniverseConfig(
            legacy_symbols=universe_config["core"]["symbols"],
            sectors={},
            fallback_mode="preserve_order",
        )

    # Parse new sector format
    sectors = {}
    sectors_config = universe_config.get("sectors", {})

    for sector_name, sector_data in sectors_config.items():
        sectors[sector_name] = SectorConfig(
            name=sector_name,
            symbols=sector_data.get("symbols", []),
            enabled=sector_data.get("enabled", True),
            description=sector_data.get("description", ""),
        )

    fallback_mode = universe_config.get("fallback_mode", "preserve_order")

    return UniverseConfig(sectors=sectors, fallback_mode=fallback_mode, legacy_symbols=None)
