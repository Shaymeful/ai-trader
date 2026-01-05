"""Candidate schema definitions for selector-to-execution pipeline.

Defines the contract between the selector layer (AI/news) and execution layer (strategies).
Candidates represent potential trading opportunities with metadata for filtering and attribution.
"""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Action(str, Enum):
    """Candidate action recommendation."""

    BUY = "buy"
    SELL = "sell"
    WATCH = "watch"  # Monitor but don't trade
    AVOID = "avoid"  # Explicitly avoid trading


class Horizon(str, Enum):
    """Trading time horizon for the candidate."""

    INTRADAY = "intraday"  # Same-day trades
    SWING = "swing"  # Multi-day trades (2-10 days)
    LONG = "long"  # Longer-term positions (weeks+)


class Candidate(BaseModel):
    """Trading candidate from selector layer.

    Represents a potential trading opportunity identified by the selector
    (AI/news/screener). Strategies consume candidates and apply their own
    confirmation logic before generating intents.
    """

    # Core identification
    candidate_id: str = Field(
        ...,
        description="Stable unique identifier for this candidate (e.g., UUID or composite key)",
        min_length=1,
    )
    created_at: str = Field(
        ...,
        description="ISO 8601 timestamp when candidate was created (UTC)",
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
    )
    expires_at: str = Field(
        ...,
        description="ISO 8601 timestamp when candidate expires (UTC)",
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
    )

    # Trading details
    symbol: str = Field(..., description="Trading symbol (e.g., AAPL, SPY)", min_length=1)
    action: Action = Field(..., description="Recommended action (buy/sell/watch/avoid)")
    confidence: float = Field(
        ...,
        description="Confidence score from selector (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )
    horizon: Horizon = Field(..., description="Expected trading time horizon")

    # Optional metadata
    sector: str | None = Field(
        None, description="Sector classification (e.g., Technology, Healthcare)"
    )
    event_type: str | None = Field(
        None,
        description="Type of event that triggered this candidate (e.g., earnings, news, technical)",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Additional tags for filtering (e.g., momentum, breakout, reversal)",
    )
    reason: str | None = Field(None, description="Human-readable reason for this candidate")
    avg_dollar_volume: float | None = Field(
        None,
        description="Average daily dollar volume for liquidity filtering",
        ge=0.0,
    )

    @field_validator("created_at", "expires_at")
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that timestamps are valid ISO 8601 format."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}") from e
        return v

    def is_expired(self, now: datetime | None = None) -> bool:
        """Check if candidate has expired.

        Args:
            now: Current time (defaults to datetime.utcnow())

        Returns:
            True if candidate has expired
        """
        if now is None:
            now = datetime.utcnow()

        expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        # Make expires timezone-naive for comparison if now is naive
        if now.tzinfo is None and expires.tzinfo is not None:
            expires = expires.replace(tzinfo=None)

        return now >= expires

    def is_tradeable(self) -> bool:
        """Check if candidate is tradeable (buy or sell action).

        Returns:
            True if action is BUY or SELL
        """
        return self.action in (Action.BUY, Action.SELL)


def load_snapshot(path: str | Path = "out/selector/snapshot.json") -> list[Candidate]:
    """Load candidates from snapshot file.

    Args:
        path: Path to snapshot file (default: out/selector/snapshot.json)

    Returns:
        List of Candidate objects

    Raises:
        FileNotFoundError: If snapshot file doesn't exist
        ValueError: If JSON is invalid or candidates fail validation
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Candidate snapshot not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # Handle both list format and dict with "candidates" key
    if isinstance(data, dict) and "candidates" in data:
        candidates_data = data["candidates"]
    elif isinstance(data, list):
        candidates_data = data
    else:
        raise ValueError("Invalid snapshot format: expected list or dict with 'candidates' key")

    return [Candidate(**candidate) for candidate in candidates_data]


def write_snapshot(
    candidates: list[Candidate],
    path: str | Path = "out/selector/snapshot.json",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write candidates to snapshot file.

    Args:
        candidates: List of Candidate objects to write
        path: Path to snapshot file (default: out/selector/snapshot.json)
        metadata: Optional metadata dict (e.g., generated_at, source)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(candidates),
        "candidates": [candidate.model_dump() for candidate in candidates],
    }

    if metadata:
        snapshot["metadata"] = metadata

    # Atomic write: write to temp file, then rename
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)

    temp_path.replace(path)


def append_event(
    event_type: str,
    data: dict[str, Any],
    path: str | Path = "out/selector/events.jsonl",
) -> None:
    """Append event to JSONL event log.

    Args:
        event_type: Type of event (e.g., candidate_loaded, candidate_selected)
        data: Event data dictionary
        path: Path to events file (default: out/selector/events.jsonl)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": event_type,
        **data,
    }

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
