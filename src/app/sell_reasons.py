"""Sell reason codes for tracking why positions are liquidated.

This module defines standardized reason codes for all sell decisions,
enabling clear audit trails and explainability.
"""

from enum import Enum


class SellReason(str, Enum):
    """Standardized sell reason codes."""

    # Capital management
    CAP_EXCEEDED = "CAP_EXCEEDED"  # Total capital exceeds max_gross_exposure_usd
    CAPITAL_REBALANCE = "CAPITAL_REBALANCE"  # Proactive rebalancing to stay under cap

    # Universe rotation
    SECTOR_DISABLED = "SECTOR_DISABLED"  # Sector was disabled in UI
    TICKER_EXCLUDED_NEWS = "TICKER_EXCLUDED_NEWS"  # Bad news exclusion from AI evaluator
    TICKER_REMOVED = "TICKER_REMOVED"  # Ticker removed from universe manually

    # Risk management
    STOP_LOSS = "STOP_LOSS"  # Stop loss triggered
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"  # Daily loss limit approaching
    POSITION_RISK = "POSITION_RISK"  # Position-specific risk event

    # Signal-based
    STRATEGY_EXIT = "STRATEGY_EXIT"  # Strategy generated sell signal
    SELL_SCANNER = "SELL_SCANNER"  # Sell scanner identified adverse conditions
    EXIT_ADVISOR = "EXIT_ADVISOR"  # Exit advisor recommended exit

    # Administrative
    MANUAL = "MANUAL"  # Manual operator intervention
    ERROR_CORRECTION = "ERROR_CORRECTION"  # Correcting erroneous position


def get_reason_priority(reason: SellReason) -> int:
    """
    Get priority for sell reason (lower number = higher priority).

    When multiple sell reasons apply to same position, highest priority wins.

    Priority order:
    1. Risk management (stop loss, daily loss limit)
    2. Capital management (cap exceeded)
    3. Universe exclusions (bad news, sector disabled)
    4. Strategy/scanner signals
    5. Manual/administrative

    Args:
        reason: Sell reason to get priority for

    Returns:
        Priority value (1 = highest priority)
    """
    priority_map = {
        # Tier 1: Risk management (highest priority)
        SellReason.STOP_LOSS: 1,
        SellReason.DAILY_LOSS_LIMIT: 2,
        SellReason.POSITION_RISK: 3,
        # Tier 2: Capital management
        SellReason.CAP_EXCEEDED: 10,
        SellReason.CAPITAL_REBALANCE: 11,
        # Tier 3: Universe exclusions
        SellReason.TICKER_EXCLUDED_NEWS: 20,
        SellReason.SECTOR_DISABLED: 21,
        SellReason.TICKER_REMOVED: 22,
        # Tier 4: Signal-based
        SellReason.SELL_SCANNER: 30,
        SellReason.EXIT_ADVISOR: 31,
        SellReason.STRATEGY_EXIT: 32,
        # Tier 5: Administrative
        SellReason.MANUAL: 40,
        SellReason.ERROR_CORRECTION: 41,
    }

    return priority_map.get(reason, 999)


def format_reason_for_logging(reason: SellReason, context: dict) -> str:
    """
    Format sell reason with context for logging.

    Args:
        reason: Sell reason
        context: Additional context (symbol, quantity, exposure, etc.)

    Returns:
        Formatted string for logs
    """
    symbol = context.get("symbol", "UNKNOWN")
    qty = context.get("quantity", 0)
    notional = context.get("notional", 0.0)

    base = f"SELL {symbol} qty={qty} notional=${notional:.2f} reason={reason.value}"

    # Add reason-specific context
    if reason == SellReason.CAP_EXCEEDED:
        current_exp = context.get("current_exposure", 0.0)
        cap = context.get("cap", 0.0)
        base += f" current_exposure=${current_exp:.2f} cap=${cap:.2f}"
    elif reason == SellReason.SECTOR_DISABLED:
        sector = context.get("sector", "UNKNOWN")
        base += f" sector={sector}"
    elif reason == SellReason.TICKER_EXCLUDED_NEWS:
        confidence = context.get("confidence", 0.0)
        rationale = context.get("rationale", "")
        base += f" confidence={confidence:.2f} rationale='{rationale[:100]}'"

    return base
