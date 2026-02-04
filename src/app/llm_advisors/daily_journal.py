"""
Daily Journal Generator - AI-powered end-of-day trading summary.

Generates a markdown journal entry summarizing the day's trading activity,
including positions opened/closed, P&L, key events, and lessons learned.

SAFETY:
- Advisory-only (for record-keeping and reflection)
- Runs once per day (idempotent - checks if journal exists)
- Gracefully degrades on LLM failures
- Budget-gated via CoPilotClient
"""

import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

from src.app.config import Config
from src.app.llm_advisors.client import CoPilotClient

logger = logging.getLogger("ai-trader.copilot.journal")


def generate_daily_journal(
    client: CoPilotClient,
    config: Config,
    date_str: str | None = None,
    summary_data: dict[str, Any] | None = None,
    force: bool = False,
) -> str | None:
    """
    Generate daily trading journal (once per day).

    Args:
        client: CoPilot client (budget-gated)
        config: Application configuration
        date_str: Date string (YYYY-MM-DD) or None for today
        summary_data: Optional summary data (positions, P&L, events, etc.)
        force: Force regeneration even if journal exists

    Returns:
        Path to generated journal file, or None if failed/disabled

    Safety:
        - Never raises exceptions
        - Returns None if disabled or failed
        - Respects budget gates via client
        - Idempotent (skips if journal already exists)
    """
    # Check if feature is enabled
    if not config.ai_copilot_daily_journal_enabled:
        logger.debug("Daily journal disabled")
        return None

    # Determine date
    if date_str is None:
        date_str = date.today().isoformat()

    # Check if journal already exists (idempotency)
    journal_dir = Path("logs/journal")
    journal_path = journal_dir / f"{date_str}.md"

    if journal_path.exists() and not force:
        logger.info(f"Journal already exists: {journal_path}")
        return str(journal_path)

    # Build prompt from summary data
    prompt = _build_journal_prompt(date_str, summary_data)

    # Define JSON schema (we'll convert to markdown)
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Journal title"},
            "summary": {
                "type": "string",
                "description": "High-level summary paragraph (2-3 sentences)",
            },
            "highlights": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 key highlights or takeaways",
            },
            "performance": {
                "type": "string",
                "description": "Performance analysis (P&L, win rate, etc.)",
            },
            "lessons": {
                "type": "array",
                "items": {"type": "string"},
                "description": "1-3 lessons learned or observations",
            },
            "outlook": {
                "type": "string",
                "description": "Brief outlook for tomorrow (1-2 sentences)",
            },
        },
        "required": ["title", "summary", "highlights", "performance", "lessons", "outlook"],
    }

    # Call LLM (budget-gated, with retries)
    # Pass feature-specific max tokens for budget enforcement
    result = client.generate_advisory_json(
        prompt=prompt,
        schema=schema,
        temperature=0.8,  # Slightly higher for more natural writing
        feature_name="daily_journal",
        feature_max_tokens=config.ai_copilot_daily_journal_max_tokens,
    )

    if result is None:
        logger.warning("Failed to generate daily journal")
        return None

    # Convert JSON to markdown
    markdown = _format_journal_markdown(date_str, result, summary_data)

    # Write journal to file
    try:
        journal_dir.mkdir(parents=True, exist_ok=True)

        # Check for trading disabled or dry-run
        from src.app.llm_advisors.utils import is_trading_disabled

        if is_trading_disabled():
            logger.info(f"Trading disabled - skipping journal write: {journal_path}")
            return None

        if config.ai_copilot_dry_run or os.getenv("AI_COPILOT_DRY_RUN") == "1":
            logger.info(f"DRY RUN - would write journal to: {journal_path}")
            return None

        with open(journal_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        logger.info(f"Generated daily journal: {journal_path}")
        return str(journal_path)

    except Exception as e:
        logger.error(f"Failed to write journal: {e}")
        return None


def _build_journal_prompt(date_str: str, summary_data: dict[str, Any] | None) -> str:
    """Build journal generation prompt from summary data."""
    prompt = f"""You are an AI trading analyst. Write a concise daily journal entry for {date_str}.

TASK:
Summarize today's trading activity in a clear, professional manner.
Focus on key events, performance, and lessons learned.
"""

    if not summary_data:
        prompt += "\n(No trading data available for today)\n"
        return prompt

    # Add trading data
    prompt += "\nTRADING DATA:\n"

    if "positions_opened" in summary_data:
        positions = summary_data["positions_opened"]
        if positions:
            prompt += f"Positions Opened: {len(positions)} ({', '.join(positions)})\n"
        else:
            prompt += "Positions Opened: None\n"

    if "positions_closed" in summary_data:
        positions = summary_data["positions_closed"]
        if positions:
            prompt += f"Positions Closed: {len(positions)} ({', '.join(positions)})\n"
        else:
            prompt += "Positions Closed: None\n"

    if "realized_pnl" in summary_data:
        pnl = summary_data["realized_pnl"]
        prompt += f"Realized P&L: ${pnl:,.2f}\n"

    if "unrealized_pnl" in summary_data:
        pnl = summary_data["unrealized_pnl"]
        prompt += f"Unrealized P&L: ${pnl:,.2f}\n"

    if "total_trades" in summary_data:
        prompt += f"Total Trades: {summary_data['total_trades']}\n"

    if "win_rate" in summary_data:
        prompt += f"Win Rate: {summary_data['win_rate']:.1%}\n"

    if "key_events" in summary_data:
        events = summary_data["key_events"]
        if events:
            prompt += f"\nKey Events:\n"
            for event in events:
                prompt += f"- {event}\n"

    if "strategy_performance" in summary_data:
        perf = summary_data["strategy_performance"]
        prompt += f"\nStrategy Performance:\n"
        for strategy, metrics in perf.items():
            prompt += f"- {strategy}: {metrics}\n"

    return prompt


def _format_journal_markdown(
    date_str: str, journal_data: dict[str, Any], summary_data: dict[str, Any] | None
) -> str:
    """Format journal data as markdown."""
    lines = [
        f"# {journal_data.get('title', f'Trading Journal - {date_str}')}",
        "",
        f"**Date:** {date_str}",
        f"**Generated by:** AI Co-Pilot",
        "",
        "---",
        "",
        "## Summary",
        "",
        journal_data.get("summary", "No summary available."),
        "",
        "## Highlights",
        "",
    ]

    # Add highlights
    highlights = journal_data.get("highlights", [])
    if highlights:
        for highlight in highlights:
            lines.append(f"- {highlight}")
    else:
        lines.append("- No highlights")

    lines.extend(
        [
            "",
            "## Performance",
            "",
            journal_data.get("performance", "No performance data."),
            "",
        ]
    )

    # Add raw metrics if available
    if summary_data:
        lines.append("### Metrics")
        lines.append("")
        if "realized_pnl" in summary_data:
            lines.append(f"- **Realized P&L:** ${summary_data['realized_pnl']:,.2f}")
        if "unrealized_pnl" in summary_data:
            lines.append(f"- **Unrealized P&L:** ${summary_data['unrealized_pnl']:,.2f}")
        if "total_trades" in summary_data:
            lines.append(f"- **Total Trades:** {summary_data['total_trades']}")
        if "win_rate" in summary_data:
            lines.append(f"- **Win Rate:** {summary_data['win_rate']:.1%}")
        lines.append("")

    # Add lessons learned
    lines.extend(
        [
            "## Lessons Learned",
            "",
        ]
    )

    lessons = journal_data.get("lessons", [])
    if lessons:
        for lesson in lessons:
            lines.append(f"- {lesson}")
    else:
        lines.append("- No lessons recorded")

    lines.extend(
        [
            "",
            "## Outlook",
            "",
            journal_data.get("outlook", "No outlook provided."),
            "",
            "---",
            "",
            f"*Generated on {date_str} by AI Co-Pilot*",
        ]
    )

    return "\n".join(lines)


def should_generate_journal(date_str: str | None = None) -> bool:
    """
    Check if daily journal should be generated (once per day).

    Args:
        date_str: Date string (YYYY-MM-DD) or None for today

    Returns:
        True if journal should be generated, False if already exists
    """
    if date_str is None:
        date_str = date.today().isoformat()

    journal_path = Path("logs/journal") / f"{date_str}.md"
    return not journal_path.exists()
