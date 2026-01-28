"""
Strategy Critique Advisor - AI-powered strategy performance analysis.

Generates end-of-day critique of strategy performance, including recommendations
for improvement and confidence in current approach.

SAFETY:
- Advisory-only (for learning and improvement)
- Appends to JSONL for historical tracking
- Runs once per day (idempotent - checks last entry)
- Gracefully degrades on LLM failures
- Budget-gated via CoPilotClient
"""

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

from src.app.config import Config
from src.app.llm_advisors.client import CoPilotClient

logger = logging.getLogger("ai-trader.copilot.critique")


def generate_strategy_critique(
    client: CoPilotClient,
    config: Config,
    date_str: str | None = None,
    performance_data: dict[str, Any] | None = None,
    force: bool = False,
) -> bool:
    """
    Generate strategy critique and append to memory file.

    Args:
        client: CoPilot client (budget-gated)
        config: Application configuration
        date_str: Date string (YYYY-MM-DD) or None for today
        performance_data: Performance metrics (win rate, trades, P&L, etc.)
        force: Force regeneration even if critique exists for today

    Returns:
        True if critique generated, False otherwise

    Safety:
        - Never raises exceptions
        - Returns False if disabled or failed
        - Respects budget gates via client
        - Idempotent (skips if critique already exists for today)
    """
    # Check if feature is enabled
    if not config.ai_copilot_strategy_critique_enabled:
        logger.debug("Strategy critique disabled")
        return False

    # Determine date
    if date_str is None:
        date_str = date.today().isoformat()

    # Check if critique already exists for today (idempotency)
    memory_path = Path("data/strategy_memory.jsonl")
    if not force and _has_critique_for_date(memory_path, date_str):
        logger.info(f"Critique already exists for {date_str}")
        return True

    # Build prompt from performance data
    prompt = _build_critique_prompt(date_str, performance_data)

    # Define JSON schema (per spec)
    schema = {
        "type": "object",
        "properties": {
            "what_worked": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of things that worked well today",
            },
            "what_failed": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of things that didn't work or failed",
            },
            "suggested_tweaks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific actionable suggestions for improvement",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Confidence in current strategy approach (0.0-1.0)",
            },
        },
        "required": ["what_worked", "what_failed", "suggested_tweaks", "confidence"],
    }

    # Call LLM (budget-gated, with retries)
    # Pass feature-specific max tokens for budget enforcement
    result = client.generate_advisory_json(
        prompt=prompt,
        schema=schema,
        temperature=0.8,  # Higher temp for more honest critique
        feature_name="strategy_critique",
        feature_max_tokens=config.ai_copilot_strategy_critique_max_tokens,
    )

    if result is None:
        logger.warning("Failed to generate strategy critique")
        return False

    # Append to JSONL memory file
    try:
        return _append_critique_to_memory(memory_path, date_str, result, performance_data)
    except Exception as e:
        logger.error(f"Failed to append critique to memory: {e}")
        return False


def _build_critique_prompt(date_str: str, performance_data: dict[str, Any] | None) -> str:
    """Build critique generation prompt from performance data."""
    prompt = f"""You are an AI trading strategy analyst. Provide an honest, constructive critique of today's strategy performance ({date_str}).

TASK:
Analyze the performance data and provide:
1. Honest critique (what went well, what didn't)
2. Actionable recommendations for improvement
3. Confidence in current strategy approach
4. Key strengths and weaknesses

Be specific, honest, and actionable. This is for learning and improvement.
"""

    if not performance_data:
        prompt += "\n(No performance data available for today)\n"
        return prompt

    # Add performance data
    prompt += "\nPERFORMANCE DATA:\n"

    if "total_trades" in performance_data:
        prompt += f"Total Trades: {performance_data['total_trades']}\n"

    if "win_rate" in performance_data:
        prompt += f"Win Rate: {performance_data['win_rate']:.1%}\n"

    if "realized_pnl" in performance_data:
        pnl = performance_data["realized_pnl"]
        prompt += f"Realized P&L: ${pnl:,.2f}\n"

    if "unrealized_pnl" in performance_data:
        pnl = performance_data["unrealized_pnl"]
        prompt += f"Unrealized P&L: ${pnl:,.2f}\n"

    if "avg_hold_time_hours" in performance_data:
        prompt += f"Avg Hold Time: {performance_data['avg_hold_time_hours']:.1f} hours\n"

    if "best_trade" in performance_data:
        trade = performance_data["best_trade"]
        prompt += f"Best Trade: {trade}\n"

    if "worst_trade" in performance_data:
        trade = performance_data["worst_trade"]
        prompt += f"Worst Trade: {trade}\n"

    if "market_conditions" in performance_data:
        conditions = performance_data["market_conditions"]
        prompt += f"\nMarket Conditions: {conditions}\n"

    if "positions_opened" in performance_data:
        positions = performance_data["positions_opened"]
        if positions:
            prompt += f"Positions Opened: {', '.join(positions)}\n"

    if "positions_closed" in performance_data:
        positions = performance_data["positions_closed"]
        if positions:
            prompt += f"Positions Closed: {', '.join(positions)}\n"

    if "strategy_signals" in performance_data:
        signals = performance_data["strategy_signals"]
        prompt += f"\nStrategy Signals:\n"
        for strategy, count in signals.items():
            prompt += f"- {strategy}: {count} signals\n"

    return prompt


def _append_critique_to_memory(
    memory_path: Path,
    date_str: str,
    critique_data: dict[str, Any],
    performance_data: dict[str, Any] | None,
) -> bool:
    """Append critique to JSONL memory file."""
    from src.app.llm_advisors.utils import is_trading_disabled

    # Check trading disabled or dry-run
    if is_trading_disabled():
        logger.info(f"Trading disabled - skipping critique write: {memory_path}")
        return False

    if os.getenv("AI_COPILOT_DRY_RUN") == "1":
        logger.info(f"DRY RUN - would append critique to: {memory_path}")
        return False

    # Ensure directory exists
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    # Build entry (per spec schema)
    entry = {
        "date": date_str,
        "what_worked": critique_data.get("what_worked", []),
        "what_failed": critique_data.get("what_failed", []),
        "suggested_tweaks": critique_data.get("suggested_tweaks", []),
        "confidence": critique_data.get("confidence", 0.0),
    }

    # Append to JSONL
    with open(memory_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    logger.info(f"Appended critique to memory: {memory_path}")
    return True


def _has_critique_for_date(memory_path: Path, date_str: str) -> bool:
    """Check if critique already exists for given date."""
    if not memory_path.exists():
        return False

    try:
        with open(memory_path, "r", encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line.strip())
                if entry.get("date") == date_str:
                    return True
    except Exception as e:
        logger.warning(f"Error checking memory file: {e}")

    return False


def load_recent_critiques(memory_path: Path | None = None, n: int = 7) -> list[dict[str, Any]]:
    """
    Load recent critiques from memory file.

    Args:
        memory_path: Path to memory file (default: data/strategy_memory.jsonl)
        n: Number of recent critiques to load (default 7 days)

    Returns:
        List of critique entries (most recent first)
    """
    if memory_path is None:
        memory_path = Path("data/strategy_memory.jsonl")

    if not memory_path.exists():
        return []

    critiques = []
    try:
        with open(memory_path, "r", encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line.strip())
                critiques.append(entry)
    except Exception as e:
        logger.error(f"Error loading critiques: {e}")
        return []

    # Return most recent n entries (reverse order)
    return critiques[-n:][::-1]
