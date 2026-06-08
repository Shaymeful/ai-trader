#!/usr/bin/env python
"""Force activation of pending universe changes."""

from pathlib import Path
from src.app.universe_registry import UniverseRegistry

# Load registry (will reload from file)
registry = UniverseRegistry(
    base_config_path=Path("config/config.yaml"), overrides_path=Path("out/universe_overrides.json")
)

print("Current sector states:")
for sector_name, override in registry.overrides.items():
    print(
        f"  {sector_name}: enabled={override.enabled}, active={override.active_version}, pending={override.pending_version}"
    )

# Activate pending changes
print("\nActivating pending changes...")
activated = registry.check_and_activate_pending()

if activated:
    print(f"\nActivated {len(activated)} changes:")
    for sector_name, old_version, new_version in activated:
        print(f"  {sector_name}: v{old_version} -> v{new_version}")

    # Verify
    resolution = registry.resolve()
    print(f"\nResolved universe: {len(resolution.symbols)} symbols")
    print(f"Symbols: {', '.join(resolution.symbols)}")
else:
    print("\nNo pending changes to activate")

print("\nUpdated sector states:")
for sector_name, override in registry.overrides.items():
    print(
        f"  {sector_name}: enabled={override.enabled}, active={override.active_version}, pending={override.pending_version}"
    )
