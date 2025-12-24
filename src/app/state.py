"""State persistence for restart-safety and idempotency."""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field


class BotState(BaseModel):
    """Persistent state for the trading bot."""

    run_id: str = Field(description="Current run ID")
    last_processed_timestamp: dict[str, str] = Field(
        default_factory=dict, description="Last processed timestamp per symbol (ISO format)"
    )
    submitted_client_order_ids: set[str] = Field(
        default_factory=set, description="Client order IDs submitted across runs"
    )
    daily_realized_pnl: dict[str, str] = Field(
        default_factory=dict,
        description="Daily realized PnL by date (YYYY-MM-DD -> decimal string)",
    )
    daily_date: str | None = Field(
        default=None,
        description="Current trading day (YYYY-MM-DD in US/Eastern). "
        "Used to detect day rollover and reset daily counters.",
    )


def get_today_date_eastern() -> str:
    """
    Get today's date in US/Eastern timezone as YYYY-MM-DD string.

    Returns:
        Date string in YYYY-MM-DD format (Eastern timezone)
    """
    eastern = ZoneInfo("America/New_York")
    now_eastern = datetime.now(eastern)
    return now_eastern.strftime("%Y-%m-%d")


def load_state(state_file: Path | None = None) -> BotState:
    """
    Load state from file if it exists, otherwise return default state.

    Automatically handles day rollover:
    - If daily_date != today (US/Eastern), resets daily counters
    - Updates daily_date to today
    - Prevents daily loss limit bypass via restart

    Args:
        state_file: Path to state file (defaults to out/state.json or AI_TRADER_STATE_FILE env var)

    Returns:
        BotState (always returns a valid state object, never None)
    """
    # Check for environment variable override (for testing)
    if state_file is None:
        import os

        env_path = os.getenv("AI_TRADER_STATE_FILE")
        state_file = Path(env_path) if env_path else Path("out/state.json")

    today_date = get_today_date_eastern()

    if not state_file.exists():
        state = BotState(run_id="initial")
        state.daily_date = today_date
        return state

    try:
        with open(state_file) as f:
            data = json.load(f)
            state = BotState(**data)

        # Check for day rollover (new trading day in US/Eastern)
        if state.daily_date != today_date:
            # Reset daily counters for new trading day
            state.daily_date = today_date
            # Note: We keep historical daily_realized_pnl entries, but start fresh for today
            # The get_daily_realized_pnl function will return 0 for today since it's not in the dict yet

        return state
    except Exception:
        # If state is corrupted, start fresh
        state = BotState(run_id="initial")
        state.daily_date = today_date
        return state


def save_state(state: BotState, state_file: Path | None = None):
    """
    Save state to file.

    Args:
        state: State to save
        state_file: Path to state file (defaults to out/state.json or AI_TRADER_STATE_FILE env var)
    """
    # Check for environment variable override (for testing)
    if state_file is None:
        import os

        env_path = os.getenv("AI_TRADER_STATE_FILE")
        state_file = Path(env_path) if env_path else Path("out/state.json")

    # Ensure directory exists
    state_file.parent.mkdir(exist_ok=True)

    # Convert to dict and handle sets
    state_dict = state.model_dump()
    state_dict["submitted_client_order_ids"] = list(state.submitted_client_order_ids)

    with open(state_file, "w") as f:
        json.dump(state_dict, f, indent=2)


def get_daily_realized_pnl(state: BotState, date: datetime | None = None) -> Decimal:
    """
    Get realized PnL for a specific date.

    Args:
        state: Bot state
        date: Date to query (defaults to today in US/Eastern)

    Returns:
        Realized PnL for the date (Decimal)
    """
    # Use today's date in US/Eastern timezone
    date_key = get_today_date_eastern() if date is None else date.strftime("%Y-%m-%d")

    pnl_str = state.daily_realized_pnl.get(date_key, "0")
    return Decimal(pnl_str)


def update_daily_realized_pnl(state: BotState, pnl_delta: Decimal, date: datetime | None = None):
    """
    Update realized PnL for a specific date.

    Args:
        state: Bot state to update
        pnl_delta: PnL change to add
        date: Date to update (defaults to today in US/Eastern)
    """
    # Use today's date in US/Eastern timezone
    date_key = get_today_date_eastern() if date is None else date.strftime("%Y-%m-%d")

    current_pnl = get_daily_realized_pnl(state, date)
    new_pnl = current_pnl + pnl_delta
    state.daily_realized_pnl[date_key] = str(new_pnl)


def build_client_order_id(
    symbol: str, side: str, signal_timestamp: datetime, strategy_name: str = "SMA"
) -> str:
    """
    Build deterministic idempotency key for order deduplication.

    The key is stable across program restarts and computed from:
    - strategy identifier (e.g., "SMA")
    - symbol (e.g., "AAPL")
    - side (e.g., "buy" or "sell")
    - signal bar timestamp (not wall-clock time)

    This ensures the same signal always produces the same key, preventing
    duplicate orders across multiple runs, loop iterations, or restarts.

    Format: {strategy}_{symbol}_{side}_{timestamp}

    Args:
        symbol: Trading symbol (e.g., "AAPL")
        side: Order side ("buy" or "sell")
        signal_timestamp: Timestamp of the bar that produced the signal
        strategy_name: Strategy identifier (default: "SMA")

    Returns:
        Deterministic idempotency key / client_order_id
    """
    # Format timestamp as compact string (no special chars)
    ts_str = signal_timestamp.strftime("%Y%m%d%H%M%S")

    # Build deterministic key from stable inputs only
    return f"{strategy_name}_{symbol}_{side}_{ts_str}"
