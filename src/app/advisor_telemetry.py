"""Advisor telemetry system for tracking advisor runs and providing visibility.

This module provides telemetry logging for universe advisor and exit advisor runs,
capturing what was evaluated, what was filtered, and why decisions were made.

This is READ-ONLY telemetry to increase transparency and prove the AI is active.
"""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class AdvisorRunEvent:
    """Telemetry event for a single advisor run."""

    # Core identification
    run_id: str  # UUID for this run
    advisor_type: str  # "universe_advisor" | "exit_advisor"
    started_at: str  # ISO timestamp
    finished_at: str  # ISO timestamp
    duration_seconds: float

    # LLM configuration
    providers_used: list[str]  # ["openai", "anthropic", "ensemble"]
    model_name: str | None  # "gpt-4o-mini", "claude-3-5-sonnet", etc.

    # Input scope
    universe_size: int  # Number of symbols/sectors evaluated
    news_events_count: int  # Number of news/RSS events ingested
    market_regime: str | None  # "bull_low_vol", "bear_high_vol", etc.

    # Generation results
    raw_ideas_generated: int  # Total ideas before filtering

    # Filtering breakdown
    filtered_out: dict[str, int]  # {"confidence_too_low": 5, "contradiction": 2, ...}

    # Final output
    final_proposals_count: int  # Ideas that survived all filters

    # Status
    status: str  # "success" | "partial" | "error"
    error_message: str | None  # If status is error

    # Summary
    rationale_summary: list[str]  # 1-3 bullet points explaining the run


class AdvisorTelemetry:
    """
    Telemetry logger for advisor runs.

    Logs to: out/advisor/events.jsonl
    """

    def __init__(self, output_dir: Path = Path("out/advisor")):
        """
        Initialize telemetry logger.

        Args:
            output_dir: Directory for telemetry logs
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.output_dir / "events.jsonl"

    def log_run(self, event: AdvisorRunEvent) -> None:
        """
        Log a complete advisor run event.

        Args:
            event: AdvisorRunEvent to log
        """
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event)) + "\n")

    def read_recent_runs(self, max_runs: int = 50) -> list[dict]:
        """
        Read recent advisor runs.

        Args:
            max_runs: Maximum number of runs to return

        Returns:
            List of run events (most recent first)
        """
        if not self.events_file.exists():
            return []

        runs = []
        with open(self.events_file, encoding="utf-8") as f:
            for line in f:
                try:
                    runs.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue

        # Return most recent first
        runs.reverse()
        return runs[:max_runs]


@dataclass
class AdvisorRunContext:
    """Context manager for tracking advisor runs."""

    advisor_type: str
    telemetry: AdvisorTelemetry
    providers_used: list[str]
    model_name: str | None = None
    universe_size: int = 0
    news_events_count: int = 0
    market_regime: str | None = None

    def __post_init__(self):
        self.run_id = str(uuid.uuid4())
        self.started_at = datetime.now(UTC)
        self.raw_ideas_generated = 0
        self.filtered_out = {}
        self.final_proposals_count = 0
        self.status = "success"
        self.error_message = None
        self.rationale_summary = []

    def add_raw_ideas(self, count: int) -> None:
        """Record number of raw ideas generated."""
        self.raw_ideas_generated = count

    def add_filtered(self, reason: str, count: int = 1) -> None:
        """Record ideas filtered out for a specific reason."""
        self.filtered_out[reason] = self.filtered_out.get(reason, 0) + count

    def set_final_count(self, count: int) -> None:
        """Set final proposals count."""
        self.final_proposals_count = count

    def set_status(self, status: str, error: str | None = None) -> None:
        """Set run status."""
        self.status = status
        self.error_message = error

    def add_rationale(self, rationale: str) -> None:
        """Add a rationale bullet point."""
        self.rationale_summary.append(rationale)

    def finalize(self) -> AdvisorRunEvent:
        """Finalize and return the run event."""
        finished_at = datetime.now(UTC)
        duration = (finished_at - self.started_at).total_seconds()

        return AdvisorRunEvent(
            run_id=self.run_id,
            advisor_type=self.advisor_type,
            started_at=self.started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_seconds=duration,
            providers_used=self.providers_used,
            model_name=self.model_name,
            universe_size=self.universe_size,
            news_events_count=self.news_events_count,
            market_regime=self.market_regime,
            raw_ideas_generated=self.raw_ideas_generated,
            filtered_out=self.filtered_out,
            final_proposals_count=self.final_proposals_count,
            status=self.status,
            error_message=self.error_message,
            rationale_summary=self.rationale_summary,
        )


def create_telemetry_context(
    advisor_type: str,
    providers: list[str],
    model_name: str | None = None,
    universe_size: int = 0,
    news_count: int = 0,
    regime: str | None = None,
) -> AdvisorRunContext:
    """
    Create a telemetry context for tracking an advisor run.

    Args:
        advisor_type: "universe_advisor" or "exit_advisor"
        providers: List of provider names used
        model_name: LLM model name
        universe_size: Number of symbols/sectors evaluated
        news_count: Number of news events ingested
        regime: Market regime string

    Returns:
        AdvisorRunContext for tracking the run
    """
    telemetry = AdvisorTelemetry()
    return AdvisorRunContext(
        advisor_type=advisor_type,
        telemetry=telemetry,
        providers_used=providers,
        model_name=model_name,
        universe_size=universe_size,
        news_events_count=news_count,
        market_regime=regime,
    )
