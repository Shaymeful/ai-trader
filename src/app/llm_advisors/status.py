"""
AI Co-Pilot Status Snapshot Writer.

Writes status snapshots to disk for UI monitoring and debugging.
Tracks budget usage, feature status, and run history.

SAFETY:
- Lightweight (no LLM calls)
- Never blocks loop
- Graceful degradation on write failures
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.app.config import Config
from src.app.llm_advisors.client import CoPilotClient

logger = logging.getLogger("ai-trader.copilot.status")


class StatusSnapshot:
    """Status snapshot for AI Co-Pilot monitoring."""

    def __init__(
        self,
        client: CoPilotClient,
        config: Config,
        run_start_time: datetime | None = None,
    ):
        """
        Initialize status snapshot.

        Args:
            client: CoPilot client
            config: Application configuration
            run_start_time: Run start timestamp (defaults to now)
        """
        self.client = client
        self.config = config
        self.run_start_time = run_start_time or datetime.now()

        # Feature execution tracking
        self.trade_rationale_calls = 0
        self.trade_rationale_successes = 0
        self.daily_journal_generated = False
        self.strategy_critique_generated = False

        # Error tracking
        self.errors: list[str] = []

    def record_trade_rationale_call(self, success: bool):
        """Record trade rationale call."""
        self.trade_rationale_calls += 1
        if success:
            self.trade_rationale_successes += 1

    def record_daily_journal_generated(self):
        """Record daily journal generation."""
        self.daily_journal_generated = True

    def record_strategy_critique_generated(self):
        """Record strategy critique generation."""
        self.strategy_critique_generated = True

    def record_error(self, error: str):
        """Record error message."""
        self.errors.append(error)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert snapshot to dict for serialization.

        Returns:
            Status dict with all monitoring data
        """
        from src.app.llm_advisors.utils import is_trading_disabled

        trading_disabled = is_trading_disabled()
        forced_reason = None
        if trading_disabled:
            forced_reason = "forced_off_by_trading_disable"

        # Determine artifact paths
        from datetime import date

        today = date.today().isoformat()
        journal_path = Path(f"logs/journal/{today}.md")
        critique_path = Path("data/strategy_memory.jsonl")

        return {
            "timestamp": datetime.now().isoformat(),
            "run_start_time": self.run_start_time.isoformat(),
            "trading_disabled_effective": trading_disabled,
            "ai_copilot_enabled_effective": self.config.ai_copilot_enabled and not trading_disabled,
            "forced_reason": forced_reason,
            "enabled": self.config.ai_copilot_enabled,
            "influence_decisions": self.config.ai_copilot_influence_decisions,
            "model": self.config.ai_copilot_model,
            "budgets": {
                "max_calls_per_run": self.config.ai_copilot_max_calls_per_run,
                "calls_used": self.client.call_count,
                "global_max_output_tokens": self.config.ai_copilot_global_max_output_tokens,
            },
            "features": {
                "trade_rationale": {
                    "enabled": self.config.ai_copilot_trade_rationale_enabled,
                    "ran": self.trade_rationale_calls > 0,
                    "skipped_reason": None
                    if self.trade_rationale_calls > 0
                    else (
                        "trading_disabled"
                        if trading_disabled
                        else "budget_exhausted"
                        if self.client.get_remaining_budget() == 0
                        else None
                    ),
                },
                "daily_journal": {
                    "enabled": self.config.ai_copilot_daily_journal_enabled,
                    "ran": self.daily_journal_generated,
                    "skipped_reason": None
                    if self.daily_journal_generated
                    else ("trading_disabled" if trading_disabled else None),
                },
                "strategy_critique": {
                    "enabled": self.config.ai_copilot_strategy_critique_enabled,
                    "ran": self.strategy_critique_generated,
                    "skipped_reason": None
                    if self.strategy_critique_generated
                    else ("trading_disabled" if trading_disabled else None),
                },
            },
            "artifacts": {
                "latest_journal_path": str(journal_path) if journal_path.exists() else None,
                "latest_critique_path": str(critique_path) if critique_path.exists() else None,
            },
            "errors": self.errors,
        }

    def write_snapshot(self, path: str | Path = "logs/ai_copilot/latest_status.json") -> bool:
        """
        Write snapshot to disk.

        Args:
            path: Path to status file (default: logs/ai_copilot/latest_status.json)

        Returns:
            True if successful, False otherwise

        Safety:
            - Never raises exceptions
            - Creates directories as needed
            - Atomic write with temp file
        """
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)

            # Convert to dict
            snapshot_data = self.to_dict()

            # Atomic write: write to temp, then rename
            temp_path = path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(snapshot_data, f, indent=2)

            temp_path.replace(path)

            logger.debug(f"Wrote status snapshot: {path}")
            return True

        except Exception as e:
            logger.error(f"Failed to write status snapshot: {e}")
            return False


def load_latest_status(
    path: str | Path = "logs/ai_copilot/latest_status.json",
) -> dict[str, Any] | None:
    """
    Load latest status snapshot from disk.

    Args:
        path: Path to status file

    Returns:
        Status dict if successful, None otherwise

    Safety:
        - Never raises exceptions
        - Returns None if file doesn't exist or can't be read
    """
    try:
        path = Path(path)

        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        logger.error(f"Failed to load status snapshot: {e}")
        return None


def write_run_summary(
    snapshot: StatusSnapshot,
    summary_data: dict[str, Any] | None = None,
    path: str | Path = "logs/ai_copilot/run_history.jsonl",
) -> bool:
    """
    Append run summary to history file (JSONL).

    Args:
        snapshot: Status snapshot
        summary_data: Optional additional summary data
        path: Path to history file

    Returns:
        True if successful, False otherwise

    Safety:
        - Never raises exceptions
        - Creates directories as needed
        - Appends to JSONL file
    """
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Build entry
        entry = {
            "timestamp": datetime.now().isoformat(),
            "run_start_time": snapshot.run_start_time.isoformat(),
            "status": snapshot.to_dict(),
        }

        if summary_data:
            entry["summary"] = summary_data

        # Append to JSONL
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        logger.debug(f"Appended run summary: {path}")
        return True

    except Exception as e:
        logger.error(f"Failed to write run summary: {e}")
        return False
