"""CLI entry point for running RSS selector once."""

import sys
from pathlib import Path

from src.app.selector.rss_selector import RSSSelector


def main() -> int:
    """Run RSS selector once and write candidates to snapshot."""
    print("RSS Selector - Automation & Energy")
    print("=" * 50)

    try:
        # Initialize selector
        selector = RSSSelector()
        print(f"Loaded config: {selector.config_path}")
        print(f"Enabled sectors: {', '.join(selector.config.sectors_enabled)}")
        print(f"RSS feeds configured: {len(selector.config.rss_feeds)}")
        print()

        # Run selector
        print("Fetching and processing RSS feeds...")
        candidates, events = selector.run()

        print(f"Processed {len(events)} events")
        print(f"Generated {len(candidates)} candidates")
        print()

        # Count by action
        action_counts = {"buy": 0, "sell": 0, "watch": 0}
        for candidate in candidates:
            action_counts[candidate.action] += 1

        print("Candidates by action:")
        for action, count in action_counts.items():
            print(f"  {action.upper()}: {count}")
        print()

        # Count by sector
        sector_counts: dict[str, int] = {}
        for candidate in candidates:
            sector = candidate.sector or "unknown"
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

        print("Candidates by sector:")
        for sector, count in sorted(sector_counts.items()):
            print(f"  {sector}: {count}")
        print()

        # Write outputs
        output_dir = "out/selector"
        print(f"Writing snapshot to {output_dir}/snapshot.json")
        selector.write_snapshot(candidates, output_dir)

        print(f"Appending events to {output_dir}/events.jsonl")
        selector.write_events(events, output_dir)

        # Check if snapshot was created
        snapshot_path = Path(output_dir) / "snapshot.json"
        if snapshot_path.exists():
            print(f"\nSnapshot size: {snapshot_path.stat().st_size} bytes")

        print("\nSelector run completed successfully!")
        return 0

    except FileNotFoundError as e:
        print(f"\nERROR: Configuration file not found: {e}", file=sys.stderr)
        print(
            "Please create config/selector.yaml with RSS feeds and sector rules.",
            file=sys.stderr,
        )
        return 1

    except Exception as e:
        print(f"\nERROR: Selector failed: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
