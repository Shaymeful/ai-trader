"""Generate sample candidate snapshot for development and testing.

Usage:
    python -m src.app.candidates.sample_snapshot [--force] [--output PATH]
"""

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.app.candidates.schema import Action, Candidate, Horizon, write_snapshot


def generate_sample_candidates() -> list[Candidate]:
    """Generate sample candidates for testing.

    Returns:
        List of 3 sample candidates with varied attributes
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    expires = now + timedelta(hours=6)

    candidates = [
        Candidate(
            candidate_id="sample-001",
            created_at=now.isoformat() + "Z",
            expires_at=expires.isoformat() + "Z",
            symbol="AAPL",
            action=Action.BUY,
            confidence=0.85,
            horizon=Horizon.INTRADAY,
            sector="Technology",
            event_type="earnings_beat",
            tags=["momentum", "breakout"],
            reason="Strong earnings beat with positive guidance",
            avg_dollar_volume=50_000_000_000.0,
        ),
        Candidate(
            candidate_id="sample-002",
            created_at=now.isoformat() + "Z",
            expires_at=expires.isoformat() + "Z",
            symbol="SPY",
            action=Action.BUY,
            confidence=0.72,
            horizon=Horizon.SWING,
            sector=None,
            event_type="technical",
            tags=["trend_following"],
            reason="Bullish crossover on daily chart",
            avg_dollar_volume=25_000_000_000.0,
        ),
        Candidate(
            candidate_id="sample-003",
            created_at=now.isoformat() + "Z",
            expires_at=expires.isoformat() + "Z",
            symbol="TSLA",
            action=Action.WATCH,
            confidence=0.65,
            horizon=Horizon.INTRADAY,
            sector="Automotive",
            event_type="news",
            tags=["volatility"],
            reason="High volatility, waiting for confirmation",
            avg_dollar_volume=15_000_000_000.0,
        ),
    ]

    return candidates


def main() -> None:
    """CLI entry point for generating sample snapshot."""
    parser = argparse.ArgumentParser(
        description="Generate sample candidate snapshot for development/testing"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing snapshot file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("out/selector/snapshot.json"),
        help="Output path for snapshot (default: out/selector/snapshot.json)",
    )

    args = parser.parse_args()

    # Check if file exists and force not specified
    if args.output.exists() and not args.force:
        print(f"Error: {args.output} already exists. Use --force to overwrite.")
        return

    # Generate and write candidates
    candidates = generate_sample_candidates()

    write_snapshot(
        candidates,
        args.output,
        metadata={"source": "sample_snapshot.py", "description": "Development test data"},
    )

    print(f"Generated {len(candidates)} sample candidates")
    print(f"Written to: {args.output}")
    print("\nCandidates:")
    for candidate in candidates:
        print(
            f"  - {candidate.symbol} ({candidate.action.value}): "
            f"confidence={candidate.confidence:.2f}, horizon={candidate.horizon.value}"
        )


if __name__ == "__main__":
    main()
