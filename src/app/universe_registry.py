"""Universe registry with sector enable/disable persistence.

Provides runtime control over which sectors are included in the trading universe.
Follows the same persistence pattern as StrategyRegistry (atomic writes + version tracking).
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from src.app.config import load_yaml_config
from src.app.universe import (
    SectorConfig,
    UniverseResolution,
    load_universe_config,
    resolve_universe,
)

logger = logging.getLogger("ai-trader")


@dataclass
class SectorOverride:
    """Sector configuration override."""

    enabled: bool
    active_version: int
    pending_version: int | None
    last_modified: str | None
    # Ticker overrides (None = use base config, [] = empty, [...] = custom list)
    tickers: list[str] | None = None


@dataclass
class UniverseOverrides:
    """Complete universe override state."""

    sectors: dict[str, SectorOverride]
    registry_version: int
    last_saved: str


class UniverseRegistry:
    """Registry for universe sector configuration with persistence."""

    def __init__(
        self,
        base_config_path: Path = Path("config/config.yaml"),
        overrides_path: Path = Path("out/universe_overrides.json"),
    ):
        """Initialize registry with base config and overrides.

        Args:
            base_config_path: Path to base YAML config
            overrides_path: Path to overrides JSON file
        """
        self.base_config_path = base_config_path
        self.overrides_path = overrides_path
        self.sectors: dict[str, SectorConfig] = {}  # Merged config
        self.overrides: dict[str, SectorOverride] = {}  # Override state
        self.load()

    def load(self) -> None:
        """Load base config and apply overrides."""
        # 1. Load base config from YAML
        if not self.base_config_path.exists():
            raise FileNotFoundError(f"Base config not found: {self.base_config_path}")

        yaml_config = load_yaml_config(self.base_config_path)
        universe_config = load_universe_config(yaml_config)

        # 2. Parse sectors from base config
        self.sectors = universe_config.sectors.copy()

        if not self.sectors:
            logger.warning("No sectors found in base config")

        # 3. Load overrides from JSON (if exists)
        overrides_data = self._load_overrides()

        # 4. Apply overrides to sectors
        if overrides_data:
            self._apply_overrides(overrides_data)

        logger.info(f"Universe registry loaded: {len(self.sectors)} sectors configured")

    def _load_overrides(self) -> dict:
        """Load overrides from JSON file.

        Returns:
            Override data dict, or empty dict if file doesn't exist
        """
        if not self.overrides_path.exists():
            logger.debug("No overrides file found (using base config)")
            return {}

        try:
            with open(self.overrides_path, encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"Loaded overrides from {self.overrides_path}")
                return data
        except Exception as e:
            logger.error(f"Failed to load overrides from {self.overrides_path}: {e}")
            return {}

    def _apply_overrides(self, overrides_data: dict) -> None:
        """Apply overrides to sector configs.

        Args:
            overrides_data: Parsed override JSON data
        """
        sector_overrides = overrides_data.get("sectors", {})

        for sector_name, override_data in sector_overrides.items():
            # Only apply to known sectors (safe)
            if sector_name not in self.sectors:
                logger.warning(f"Override for unknown sector '{sector_name}' (ignoring)")
                continue

            # Parse override
            override = SectorOverride(
                enabled=override_data.get("enabled", True),
                active_version=override_data.get("active_version", 1),
                pending_version=override_data.get("pending_version"),
                last_modified=override_data.get("last_modified"),
                tickers=override_data.get("tickers"),
            )

            # Apply to sector config
            self.sectors[sector_name].enabled = override.enabled
            # Apply ticker overrides if present
            if override.tickers is not None:
                self.sectors[sector_name].symbols = override.tickers
            self.overrides[sector_name] = override

            logger.debug(
                f"Applied override to '{sector_name}': enabled={override.enabled}, "
                f"tickers={len(override.tickers) if override.tickers else 'base'}"
            )

    def stage_change(self, sector_name: str, enabled: bool) -> int:
        """Stage a sector enable/disable change.

        Changes are saved immediately but activate on next loop tick.

        Args:
            sector_name: Name of sector to modify
            enabled: New enabled state

        Returns:
            New pending version number

        Raises:
            ValueError: If sector name is invalid
        """
        # 1. Validate sector exists
        if sector_name not in self.sectors:
            raise ValueError(f"Unknown sector: {sector_name}")

        # 2. Update in-memory config
        self.sectors[sector_name].enabled = enabled

        # 3. Update or create override
        if sector_name in self.overrides:
            override = self.overrides[sector_name]
            override.pending_version = (override.active_version or 0) + 1
        else:
            override = SectorOverride(
                enabled=enabled,
                active_version=0,
                pending_version=1,
                last_modified=None,
            )
            self.overrides[sector_name] = override

        # 4. Update timestamp
        override.last_modified = datetime.now(UTC).isoformat()

        # 5. Save overrides atomically
        self._save_overrides()

        logger.info(
            f"Staged change for '{sector_name}': enabled={enabled}, pending_version={override.pending_version}"
        )

        return override.pending_version

    def stage_constituent_change(self, sector_name: str, action: str, tickers: list[str]) -> int:
        """Stage a constituent add/remove change.

        Args:
            sector_name: Name of sector to modify
            action: "add" or "remove"
            tickers: List of tickers to add/remove

        Returns:
            New pending version number

        Raises:
            ValueError: If sector name is invalid or action is invalid
        """
        # 1. Validate sector exists
        if sector_name not in self.sectors:
            raise ValueError(f"Unknown sector: {sector_name}")

        # 2. Validate action
        if action not in ["add", "remove"]:
            raise ValueError(f"Invalid action: {action}")

        # 3. Get current ticker list (from override or base config)
        if sector_name in self.overrides and self.overrides[sector_name].tickers is not None:
            current_tickers = self.overrides[sector_name].tickers.copy()
        else:
            current_tickers = self.sectors[sector_name].symbols.copy()

        # 4. Apply action
        if action == "add":
            for ticker in tickers:
                if ticker not in current_tickers:
                    current_tickers.append(ticker)
        elif action == "remove":
            current_tickers = [t for t in current_tickers if t not in tickers]

        # 5. Update in-memory sector config
        self.sectors[sector_name].symbols = current_tickers

        # 6. Update or create override
        if sector_name in self.overrides:
            override = self.overrides[sector_name]
            override.tickers = current_tickers
            override.pending_version = (override.active_version or 0) + 1
        else:
            override = SectorOverride(
                enabled=self.sectors[sector_name].enabled,
                active_version=0,
                pending_version=1,
                last_modified=None,
                tickers=current_tickers,
            )
            self.overrides[sector_name] = override

        # 7. Update timestamp
        override.last_modified = datetime.now(UTC).isoformat()

        # 8. Save overrides atomically
        self._save_overrides()

        logger.info(
            f"Staged constituent change for '{sector_name}': action={action}, "
            f"tickers={tickers}, pending_version={override.pending_version}"
        )

        return override.pending_version

    def _save_overrides(self) -> None:
        """Save overrides to JSON atomically.

        Uses temp file + rename pattern for atomic writes.
        """
        # 1. Build JSON structure
        overrides_data = {
            "sectors": {},
            "registry_version": 1,
            "last_saved": datetime.now(UTC).isoformat(),
        }

        for sector_name, override in self.overrides.items():
            overrides_data["sectors"][sector_name] = {
                "enabled": override.enabled,
                "active_version": override.active_version,
                "pending_version": override.pending_version,
                "last_modified": override.last_modified,
                "tickers": override.tickers,
            }

        # 2. Ensure output directory exists
        self.overrides_path.parent.mkdir(parents=True, exist_ok=True)

        # 3. Write to temp file
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.overrides_path.parent,
                delete=False,
                suffix=".tmp",
            ) as tmp_file:
                json.dump(overrides_data, tmp_file, indent=2)
                tmp_path = Path(tmp_file.name)

            # 4. Atomic rename
            tmp_path.replace(self.overrides_path)
            logger.debug(f"Saved overrides to {self.overrides_path}")

        except Exception as e:
            logger.error(f"Failed to save overrides: {e}")
            # Clean up temp file if it exists
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    def check_and_activate_pending(self) -> list[tuple[str, int, int]]:
        """Activate pending changes at loop start.

        Promotes pending_version to active_version for all sectors with pending changes.

        Returns:
            List of (sector_name, old_version, new_version) for activated changes
        """
        activated = []

        for sector_name, override in self.overrides.items():
            if override.pending_version is not None:
                old_version = override.active_version
                new_version = override.pending_version

                # Promote pending to active
                override.active_version = new_version
                override.pending_version = None

                activated.append((sector_name, old_version, new_version))

        # Save updated state if any changes were activated
        if activated:
            self._save_overrides()
            logger.info(f"Activated {len(activated)} pending universe changes")

        return activated

    def reset_to_defaults(self) -> None:
        """Reset all sectors to base config defaults.

        Deletes the overrides file and reloads from base config.
        """
        # Delete overrides file if it exists
        if self.overrides_path.exists():
            self.overrides_path.unlink()
            logger.info(f"Deleted overrides file: {self.overrides_path}")

        # Clear in-memory overrides
        self.overrides.clear()

        # Reload from base config
        self.load()

        logger.info("Universe reset to defaults")

    def resolve(self) -> UniverseResolution:
        """Resolve current universe with overrides applied.

        Uses the existing resolve_universe() function but with merged config.

        Returns:
            UniverseResolution with deduplicated symbols from enabled sectors
        """
        # Build config dict with current (merged) sector state
        config_dict = {
            "universe": {
                "fallback_mode": "preserve_order",
                "sectors": {
                    name: {
                        "enabled": sector.enabled,
                        "symbols": sector.symbols,
                        "description": sector.description,
                    }
                    for name, sector in self.sectors.items()
                },
            }
        }

        # Use existing resolution logic
        return resolve_universe(config_dict)
