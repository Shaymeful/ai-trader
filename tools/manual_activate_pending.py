#!/usr/bin/env python3
"""
Manual Pending Version Activation Tool

Use this script to manually activate pending universe versions when the loop
isn't running or pending versions are stuck.

This performs the same activation that would happen automatically at the start
of each loop iteration.

Usage:
    python tools/manual_activate_pending.py

Example:
    # Activate all pending versions
    $ python tools/manual_activate_pending.py

    Activating pending universe versions...
    ✓ automation: v2 -> v3
    ✓ energy: v0 -> v1

    2 sectors activated successfully!
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.app.universe_registry import UniverseRegistry
from src.app.universe_advisor.apply import mark_applied


def main():
    print("\nManual Pending Version Activation")
    print("=" * 60)

    try:
        # Load universe registry
        print("Loading universe registry...")
        registry = UniverseRegistry()
        print(f"Loaded {len(registry.sectors)} sectors\n")

        # Check for pending versions
        print("Checking for pending versions...")
        pending_count = sum(
            1 for override in registry.overrides.values() if override.pending_version is not None
        )

        if pending_count == 0:
            print("No pending versions found. Nothing to activate.")
            return

        print(f"Found {pending_count} sector(s) with pending versions:\n")
        for sector_name, override in registry.overrides.items():
            if override.pending_version is not None:
                print(f"  {sector_name}: v{override.active_version} -> v{override.pending_version}")

        # Confirm activation
        print()
        response = input("Activate these pending versions? [y/N]: ").strip().lower()
        if response not in ["y", "yes"]:
            print("Activation cancelled.")
            return

        # Activate pending versions
        print("\nActivating pending versions...")
        activated = registry.check_and_activate_pending()

        if not activated:
            print("No versions were activated.")
            return

        # Mark related proposals as APPLIED
        proposals_file = Path("out/universe_proposals.json")
        history_file = Path("out/universe_proposals_history.jsonl")

        for sector_name, old_version, new_version in activated:
            print(f"[OK] {sector_name}: v{old_version} -> v{new_version}")

            try:
                mark_applied(sector_name, proposals_file, history_file)
            except Exception as e:
                print(f"  WARNING: Failed to mark proposals as applied: {e}")

        print(f"\n{len(activated)} sector(s) activated successfully!")
        print("\nChanges are now live. The loop will use these versions on next iteration.")

    except FileNotFoundError as e:
        print(f"ERROR: Configuration file not found: {e}")
        print("\nMake sure you're running this script from the project root directory.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Activation failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
