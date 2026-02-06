"""Ticker exclusion manager for AI-driven bad news detection.

This module maintains a list of tickers excluded from trading due to adverse news
or other AI-detected conditions. Exclusions have TTL and confidence scores.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TickerExclusion:
    """Ticker exclusion with reason and expiry."""

    symbol: str
    action: str  # "exclude", "watch", "ok"
    confidence: float  # 0.0 - 1.0
    rationale: str
    ttl_hours: int
    expires_at: datetime
    created_at: datetime
    categories: list[str]  # e.g., ["earnings_miss", "regulatory", "fraud"]
    source: str  # "ai_evaluator", "manual", etc.


class TickerExclusionManager:
    """
    Manages ticker exclusions with TTL and persistence.

    Features:
    - Add/remove exclusions with expiry
    - Rate limiting to avoid spam
    - Persistence to JSON
    - TTL-based auto-expiry
    """

    def __init__(
        self,
        exclusions_file: Path = Path("out/ticker_exclusions.json"),
        evaluations_file: Path = Path("out/ticker_evaluations.jsonl"),
    ):
        """
        Initialize exclusion manager.

        Args:
            exclusions_file: Path to exclusions JSON file
            evaluations_file: Path to evaluation history JSONL
        """
        self.exclusions_file = exclusions_file
        self.evaluations_file = evaluations_file
        self.exclusions: dict[str, TickerExclusion] = {}
        self.load()

    def load(self) -> None:
        """Load exclusions from disk."""
        # Clear existing exclusions before loading
        self.exclusions = {}

        if not self.exclusions_file.exists():
            logger.info("No exclusions file found (starting fresh)")
            return

        try:
            with open(self.exclusions_file, encoding="utf-8") as f:
                data = json.load(f)

            # Parse exclusions
            for symbol, excl_data in data.items():
                try:
                    exclusion = TickerExclusion(
                        symbol=symbol,
                        action=excl_data["action"],
                        confidence=excl_data["confidence"],
                        rationale=excl_data["rationale"],
                        ttl_hours=excl_data["ttl_hours"],
                        expires_at=datetime.fromisoformat(excl_data["expires_at"]),
                        created_at=datetime.fromisoformat(excl_data["created_at"]),
                        categories=excl_data.get("categories", []),
                        source=excl_data.get("source", "unknown"),
                    )

                    # Check if expired
                    if exclusion.expires_at > datetime.now(UTC):
                        self.exclusions[symbol] = exclusion
                    else:
                        logger.debug(f"Exclusion for {symbol} expired - removing")

                except Exception as e:
                    logger.warning(f"Failed to parse exclusion for {symbol}: {e}")

            logger.info(f"Loaded {len(self.exclusions)} active exclusions")

        except Exception as e:
            logger.error(f"Failed to load exclusions from {self.exclusions_file}: {e}")

    def save(self) -> None:
        """Save exclusions to disk (atomic write)."""
        self.exclusions_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert to serializable dict
        data = {}
        for symbol, exclusion in self.exclusions.items():
            data[symbol] = {
                "symbol": exclusion.symbol,
                "action": exclusion.action,
                "confidence": exclusion.confidence,
                "rationale": exclusion.rationale,
                "ttl_hours": exclusion.ttl_hours,
                "expires_at": exclusion.expires_at.isoformat(),
                "created_at": exclusion.created_at.isoformat(),
                "categories": exclusion.categories,
                "source": exclusion.source,
            }

        # Atomic write
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(
            mode="w",
            dir=self.exclusions_file.parent,
            delete=False,
            suffix=".tmp",
            encoding="utf-8",
        ) as tmp_file:
            json.dump(data, tmp_file, indent=2)
            tmp_path = Path(tmp_file.name)

        tmp_path.replace(self.exclusions_file)
        logger.debug(f"Saved {len(self.exclusions)} exclusions to {self.exclusions_file}")

    def add_exclusion(
        self,
        symbol: str,
        action: str,
        confidence: float,
        rationale: str,
        ttl_hours: int,
        categories: list[str] | None = None,
        source: str = "ai_evaluator",
    ) -> TickerExclusion:
        """
        Add or update ticker exclusion.

        Args:
            symbol: Ticker symbol
            action: "exclude", "watch", or "ok"
            confidence: Confidence score 0.0-1.0
            rationale: Explanation for exclusion
            ttl_hours: Hours until expiry
            categories: Optional list of categories
            source: Source of exclusion (default: "ai_evaluator")

        Returns:
            Created/updated TickerExclusion
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=ttl_hours)

        exclusion = TickerExclusion(
            symbol=symbol,
            action=action,
            confidence=confidence,
            rationale=rationale,
            ttl_hours=ttl_hours,
            expires_at=expires_at,
            created_at=now,
            categories=categories or [],
            source=source,
        )

        self.exclusions[symbol] = exclusion
        self.save()

        logger.info(
            f"Added exclusion for {symbol}: action={action}, confidence={confidence:.2f}, "
            f"ttl={ttl_hours}h, expires_at={expires_at.isoformat()}"
        )

        # Log to evaluation history
        self._log_evaluation(exclusion)

        return exclusion

    def remove_exclusion(self, symbol: str) -> bool:
        """
        Remove ticker exclusion.

        Args:
            symbol: Ticker symbol to remove

        Returns:
            True if exclusion was removed, False if not found
        """
        if symbol in self.exclusions:
            del self.exclusions[symbol]
            self.save()
            logger.info(f"Removed exclusion for {symbol}")
            return True

        return False

    def is_excluded(self, symbol: str) -> bool:
        """
        Check if ticker is currently excluded.

        Args:
            symbol: Ticker symbol

        Returns:
            True if excluded and not expired
        """
        if symbol not in self.exclusions:
            return False

        exclusion = self.exclusions[symbol]

        # Check expiry
        if exclusion.expires_at <= datetime.now(UTC):
            logger.debug(f"Exclusion for {symbol} expired - removing")
            self.remove_exclusion(symbol)
            return False

        return exclusion.action == "exclude"

    def get_exclusion(self, symbol: str) -> TickerExclusion | None:
        """
        Get exclusion details for ticker.

        Args:
            symbol: Ticker symbol

        Returns:
            TickerExclusion if exists and not expired, else None
        """
        if symbol not in self.exclusions:
            return None

        exclusion = self.exclusions[symbol]

        # Check expiry
        if exclusion.expires_at <= datetime.now(UTC):
            self.remove_exclusion(symbol)
            return None

        return exclusion

    def get_all_exclusions(self) -> dict[str, TickerExclusion]:
        """
        Get all active exclusions.

        Returns:
            Dict of {symbol: TickerExclusion}
        """
        # Remove expired exclusions
        expired = [
            symbol
            for symbol, excl in self.exclusions.items()
            if excl.expires_at <= datetime.now(UTC)
        ]

        for symbol in expired:
            self.remove_exclusion(symbol)

        return self.exclusions.copy()

    def should_evaluate(self, symbol: str, min_interval_hours: int = 24) -> bool:
        """
        Check if ticker should be re-evaluated (rate limiting).

        Args:
            symbol: Ticker symbol
            min_interval_hours: Minimum hours between evaluations

        Returns:
            True if evaluation is allowed
        """
        # Check if ticker has existing exclusion
        if symbol in self.exclusions:
            exclusion = self.exclusions[symbol]
            time_since_eval = datetime.now(UTC) - exclusion.created_at
            hours_since = time_since_eval.total_seconds() / 3600

            if hours_since < min_interval_hours:
                logger.debug(
                    f"Skipping {symbol} evaluation: "
                    f"last eval {hours_since:.1f}h ago (min: {min_interval_hours}h)"
                )
                return False

        return True

    def _log_evaluation(self, exclusion: TickerExclusion) -> None:
        """
        Log evaluation to JSONL history.

        Args:
            exclusion: TickerExclusion to log
        """
        self.evaluations_file.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": exclusion.created_at.isoformat(),
            "symbol": exclusion.symbol,
            "action": exclusion.action,
            "confidence": exclusion.confidence,
            "rationale": exclusion.rationale,
            "ttl_hours": exclusion.ttl_hours,
            "expires_at": exclusion.expires_at.isoformat(),
            "categories": exclusion.categories,
            "source": exclusion.source,
        }

        try:
            with open(self.evaluations_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to log evaluation to {self.evaluations_file}: {e}")

    def get_excluded_dict(self) -> dict[str, dict[str, Any]]:
        """
        Get exclusions in dict format for reconciler.

        Returns:
            Dict of {symbol: {reason, confidence, ttl, categories}}
        """
        result = {}
        for symbol, excl in self.get_all_exclusions().items():
            if excl.action == "exclude":
                result[symbol] = {
                    "reason": excl.rationale,
                    "confidence": excl.confidence,
                    "ttl_hours": excl.ttl_hours,
                    "categories": excl.categories,
                    "expires_at": excl.expires_at.isoformat(),
                }

        return result
