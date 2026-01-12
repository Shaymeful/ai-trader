"""Account summary utilities for loading persisted capital settings."""

import json
import logging
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger("ai-trader")


def load_account_summary() -> dict | None:
    """
    Load account summary from persisted file.

    The account summary is saved by the UI when the operator edits
    capital settings via POST /account/summary. This provides the
    "total_capital" that acts as an equity cap for allocation.

    Returns:
        Dict with account summary fields if file exists, None otherwise

    Example:
        {
            "total_capital": 30000.0,
            "max_daily_loss": 1500.0,
            "max_total_positions": 20
        }
    """
    path = Path("out/account_summary.json")

    if not path.exists():
        return None

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            logger.debug(f"Loaded account summary from {path}")
            return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load account summary from {path}: {e}")
        return None


def get_total_capital() -> Decimal | None:
    """
    Get total_capital from persisted account summary.

    This is the operator-configured capital amount that serves as
    an equity cap when use_total_capital_as_equity_cap is enabled.

    Returns:
        Total capital as Decimal if available, None otherwise
    """
    summary = load_account_summary()

    if not summary:
        return None

    if "total_capital" not in summary:
        logger.warning("Account summary exists but missing total_capital field")
        return None

    try:
        total_capital = Decimal(str(summary["total_capital"]))

        if total_capital <= 0:
            logger.warning(f"Invalid total_capital: {total_capital} (must be > 0)")
            return None

        return total_capital

    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid total_capital value in account summary: {e}")
        return None


def get_effective_equity_cap(
    broker_equity: Decimal | float,
    use_total_capital_as_cap: bool = True,
) -> Decimal:
    """
    Compute effective equity cap for allocation.

    This implements the capital utilization cap logic:
    1. If use_total_capital_as_cap is true AND total_capital exists:
       cap = min(broker_equity, total_capital)
    2. Otherwise: cap = broker_equity

    The purpose is to allow the operator to set a lower capital
    limit than what the broker reports (e.g., to reserve cash or
    test with smaller amounts).

    Args:
        broker_equity: Current broker account equity
        use_total_capital_as_cap: Whether to apply total_capital as a cap

    Returns:
        Effective equity cap (will not exceed broker_equity)

    Examples:
        >>> # Broker has $100k, operator set $30k limit
        >>> get_effective_equity_cap(100000, use_total_capital_as_cap=True)
        Decimal('30000.0')  # Capped at operator limit

        >>> # Broker has $20k, operator set $30k limit
        >>> get_effective_equity_cap(20000, use_total_capital_as_cap=True)
        Decimal('20000.0')  # Capped at broker equity (can't use more than available)

        >>> # No cap applied
        >>> get_effective_equity_cap(100000, use_total_capital_as_cap=False)
        Decimal('100000.0')  # Uses full broker equity
    """
    broker_equity_dec = Decimal(str(broker_equity))

    if not use_total_capital_as_cap:
        # No cap applied - use full broker equity
        return broker_equity_dec

    # Check if total_capital cap is configured
    total_capital = get_total_capital()

    if total_capital is None:
        # No cap configured - use full broker equity
        logger.debug("No total_capital configured, using full broker equity")
        return broker_equity_dec

    # Apply the minimum of broker equity and total_capital
    # (can't allocate more than broker has, even if operator sets higher limit)
    effective_cap = min(broker_equity_dec, total_capital)

    if effective_cap < broker_equity_dec:
        logger.info(
            f"Applying total_capital cap: broker_equity=${broker_equity_dec:.2f}, "
            f"total_capital=${total_capital:.2f}, "
            f"effective_cap=${effective_cap:.2f}"
        )

    return effective_cap
