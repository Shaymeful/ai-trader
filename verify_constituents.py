"""Verify constituent changes in UniverseRegistry.

Quick script to show current sector tickers after approving constituent proposals.
"""

from pathlib import Path

from src.app.universe_registry import UniverseRegistry


def main():
    """Display current sector constituents."""
    registry_path = Path("out/universe_overrides.json")

    if not registry_path.exists():
        print("No overrides file found. Using base config only.")

    registry = UniverseRegistry()

    print("Current Universe Constituents")
    print("=" * 60)
    print()

    for sector_name, sector_config in registry.sectors.items():
        enabled_str = "ENABLED" if sector_config.enabled else "DISABLED"
        print(f"{sector_name} ({enabled_str})")
        print(f"  Description: {sector_config.description}")
        print(f"  Tickers ({len(sector_config.symbols)}): {', '.join(sector_config.symbols)}")

        # Show override status if applicable
        if sector_name in registry.overrides:
            override = registry.overrides[sector_name]
            print(
                f"  Override: version={override.active_version}, pending={override.pending_version}"
            )
            if override.tickers is not None:
                print(f"  Custom tickers applied: {len(override.tickers)} tickers")

        print()

    # Show resolution (deduplicated universe)
    resolution = registry.resolve()
    print(f"Resolved Universe: {len(resolution.symbols)} unique tickers")
    print(f"  {', '.join(resolution.symbols[:20])}")
    if len(resolution.symbols) > 20:
        print(f"  ... and {len(resolution.symbols) - 20} more")


if __name__ == "__main__":
    main()
