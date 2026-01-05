"""Candidate store with filtering and deduplication logic.

Provides functions for loading, filtering, and managing candidate snapshots
for consumption by trading strategies.
"""

from datetime import datetime
from pathlib import Path

from src.app.candidates.schema import Candidate, load_snapshot


def load_candidates(path: str | Path = "out/selector/snapshot.json") -> list[Candidate]:
    """Load candidates from snapshot file with error handling.

    Args:
        path: Path to snapshot file

    Returns:
        List of candidates (empty list if file doesn't exist)
    """
    try:
        return load_snapshot(path)
    except FileNotFoundError:
        return []


def filter_valid(candidates: list[Candidate], now: datetime | None = None) -> list[Candidate]:
    """Filter out expired candidates.

    Args:
        candidates: List of candidates to filter
        now: Current time (defaults to datetime.utcnow())

    Returns:
        List of non-expired candidates
    """
    if now is None:
        now = datetime.utcnow()

    return [c for c in candidates if not c.is_expired(now)]


def filter_by_liquidity(
    candidates: list[Candidate],
    min_dollar_volume: float = 1_000_000.0,
) -> list[Candidate]:
    """Filter candidates by minimum average dollar volume.

    Args:
        candidates: List of candidates to filter
        min_dollar_volume: Minimum average daily dollar volume (default: $1M)

    Returns:
        List of candidates meeting liquidity requirement
        (includes candidates with no avg_dollar_volume data)
    """
    return [
        c
        for c in candidates
        if c.avg_dollar_volume is None or c.avg_dollar_volume >= min_dollar_volume
    ]


def deduplicate(candidates: list[Candidate]) -> list[Candidate]:
    """Deduplicate candidates by candidate_id, keeping the newest.

    Args:
        candidates: List of candidates (may contain duplicates)

    Returns:
        Deduplicated list (one candidate per candidate_id)
    """
    # Build map of candidate_id -> candidate, keeping newest based on created_at
    candidate_map: dict[str, Candidate] = {}

    for candidate in candidates:
        existing = candidate_map.get(candidate.candidate_id)

        if existing is None:
            candidate_map[candidate.candidate_id] = candidate
        else:
            # Keep the newer candidate
            existing_time = datetime.fromisoformat(existing.created_at.replace("Z", "+00:00"))
            candidate_time = datetime.fromisoformat(candidate.created_at.replace("Z", "+00:00"))

            if candidate_time > existing_time:
                candidate_map[candidate.candidate_id] = candidate

    return list(candidate_map.values())


def get_tradeable_candidates(
    candidates: list[Candidate],
    now: datetime | None = None,
    min_dollar_volume: float = 1_000_000.0,
) -> list[Candidate]:
    """Get filtered, deduplicated, tradeable candidates.

    Applies full filtering pipeline:
    1. Filter by expiration
    2. Filter by liquidity
    3. Deduplicate by candidate_id
    4. Filter to tradeable actions only (buy/sell)

    Args:
        candidates: Raw list of candidates
        now: Current time (defaults to datetime.utcnow())
        min_dollar_volume: Minimum average daily dollar volume

    Returns:
        Filtered list of tradeable candidates
    """
    # Apply filters in sequence
    filtered = filter_valid(candidates, now)
    filtered = filter_by_liquidity(filtered, min_dollar_volume)
    filtered = deduplicate(filtered)
    filtered = [c for c in filtered if c.is_tradeable()]

    return filtered
