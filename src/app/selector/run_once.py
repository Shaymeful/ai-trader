"""CLI entry point for running RSS selector once."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.app.selector.rss_selector import RSSSelector

# Load environment variables from .env file
load_dotenv()


def main() -> int:
    """Run RSS selector once and write candidates to snapshot."""
    parser = argparse.ArgumentParser(description="Run RSS selector once")
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print detailed statistics including rejection reasons",
    )
    args = parser.parse_args()

    print("RSS Selector - Automation & Energy")
    print("=" * 50)

    try:
        # Initialize Alpaca client for sentiment scoring (if credentials available)
        alpaca_client = None
        api_key = os.getenv("ALPACA_PAPER_KEY_ID")
        secret_key = os.getenv("ALPACA_PAPER_SECRET_KEY")

        if api_key and secret_key:
            try:
                from alpaca.data.historical import StockHistoricalDataClient

                alpaca_client = StockHistoricalDataClient(api_key, secret_key)
                print("[OK] Alpaca client initialized for sentiment scoring")
            except Exception as e:
                print(f"[WARN] Could not initialize Alpaca client: {e}")
                print("  Sentiment scoring will be disabled (falling back to keyword-based)")
        else:
            print("[WARN] No Alpaca credentials found - sentiment scoring disabled")

        print()

        # Initialize selector with Alpaca client for sentiment scoring
        selector = RSSSelector(alpaca_client=alpaca_client)
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

        # Print detailed stats if requested
        if args.stats:
            print("\nDetailed Statistics:")
            print("-" * 50)
            stats = RSSSelector.compute_stats(events)

            print(f"Headlines processed: {stats['headlines_processed']}")
            print(f"Symbols extracted: {stats['symbols_extracted']}")
            print(f"Candidates created: {stats['candidates_created']}")
            print()

            print("Rejections by reason:")
            rejection_keys = [
                ("no_sector", "No matching sector"),
                ("no_symbol", "No symbol extracted"),
                ("low_confidence", "Low confidence score"),
                ("duplicate", "Duplicate (same symbol+action)"),
                ("liquidity_floor", "Below liquidity floor"),
                ("allowlist", "Not in allowlist"),
                ("denylist", "In denylist"),
            ]

            total_rejected = 0
            for key, label in rejection_keys:
                count = stats[f"rejected_{key}"]
                total_rejected += count
                if count > 0:
                    print(f"  {label}: {count}")

            if total_rejected == 0:
                print("  (none)")

            print()

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
