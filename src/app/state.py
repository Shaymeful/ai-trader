"""State persistence for restart-safety and idempotency."""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Set

from pydantic import BaseModel, Field


class BotState(BaseModel):
    """Persistent state for the trading bot."""

    run_id: str = Field(description="Current run ID")
    last_processed_timestamp: Dict[str, str] = Field(
        default_factory=dict,
        description="Last processed timestamp per symbol (ISO format)"
    )
    submitted_client_order_ids: Set[str] = Field(
        default_factory=set,
        description="Client order IDs submitted across runs"
    )


def load_state(state_file: Path = Path("out/state.json")) -> BotState:
    """
    Load state from file if it exists, otherwise return default state.

    Args:
        state_file: Path to state file

    Returns:
        BotState (always returns a valid state object, never None)
    """
    if not state_file.exists():
        return BotState(run_id="initial")

    try:
        with open(state_file, "r") as f:
            data = json.load(f)
            return BotState(**data)
    except Exception:
        # If state is corrupted, start fresh
        return BotState(run_id="initial")


def save_state(state: BotState, state_file: Path = Path("out/state.json")):
    """
    Save state to file.

    Args:
        state: State to save
        state_file: Path to state file
    """
    # Ensure directory exists
    state_file.parent.mkdir(exist_ok=True)

    # Convert to dict and handle sets
    state_dict = state.model_dump()
    state_dict["submitted_client_order_ids"] = list(state.submitted_client_order_ids)

    with open(state_file, "w") as f:
        json.dump(state_dict, f, indent=2)


def build_client_order_id(
    run_id: str,
    symbol: str,
    side: str,
    signal_timestamp: datetime,
    strategy_name: str = "SMA"
) -> str:
    """
    Build deterministic client order ID.

    Format: {strategy}_{symbol}_{side}_{timestamp}_{run_id_prefix}

    Args:
        run_id: Run ID for this session
        symbol: Trading symbol
        side: Order side (buy/sell)
        signal_timestamp: Timestamp of the signal
        strategy_name: Strategy name (default: SMA)

    Returns:
        Deterministic client order ID
    """
    # Use only first 8 chars of run_id for brevity
    run_id_prefix = run_id[:8]

    # Format timestamp as compact string (no special chars)
    ts_str = signal_timestamp.strftime("%Y%m%d%H%M%S")

    # Build deterministic ID
    return f"{strategy_name}_{symbol}_{side}_{ts_str}_{run_id_prefix}"
