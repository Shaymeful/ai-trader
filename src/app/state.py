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


# ============================================================================
# Strategy Performance State
# ============================================================================


class StrategyState(BaseModel):
    """State for a single strategy's performance tracking."""

    name: str
    weight: float = Field(default=1.0, ge=0.0, le=1.0)  # Strategy weight (0-1)
    cumulative_pnl: float = Field(default=0.0)  # Cumulative P&L
    rolling_returns: list[float] = Field(default_factory=list)  # Limited to max_samples
    drawdown: float = Field(default=0.0)  # Current drawdown from peak
    trade_count: int = Field(default=0)  # Number of trades attributed
    last_updated: str = Field(default_factory=lambda: datetime.now().isoformat())

    def add_return(self, return_value: float, max_samples: int = 200):
        """
        Add a return sample and update rolling window.

        Args:
            return_value: Return to add
            max_samples: Maximum samples to keep (default 200)
        """
        self.rolling_returns.append(return_value)
        if len(self.rolling_returns) > max_samples:
            self.rolling_returns = self.rolling_returns[-max_samples:]
        self.last_updated = datetime.now().isoformat()

    def update_drawdown(self):
        """Update drawdown from peak equity."""
        if not self.rolling_returns:
            self.drawdown = 0.0
            return

        # Calculate equity curve
        equity = 1.0
        peak = 1.0
        max_drawdown = 0.0

        for ret in self.rolling_returns:
            equity *= 1.0 + ret
            peak = max(peak, equity)
            drawdown = (equity - peak) / peak
            max_drawdown = min(max_drawdown, drawdown)

        self.drawdown = max_drawdown


def load_strategy_state(state_dir: Path | None = None) -> dict[str, StrategyState]:
    """
    Load strategy state from disk.

    Args:
        state_dir: Directory for state files (defaults to repo_root/state)

    Returns:
        Dictionary mapping strategy name to StrategyState
    """
    if state_dir is None:
        # Default to repo_root/state
        import os

        env_path = os.getenv("AI_TRADER_STRATEGY_STATE_DIR")
        if env_path:
            state_dir = Path(env_path)
        else:
            repo_root = Path(__file__).resolve().parents[2]
            state_dir = repo_root / "state"

    state_dir = Path(state_dir)
    state_file = state_dir / "strategy_state.json"

    if not state_file.exists():
        return {}

    try:
        with open(state_file) as f:
            data = json.load(f)

        states = {}
        for name, state_dict in data.items():
            states[name] = StrategyState(**state_dict)

        return states

    except Exception:
        return {}


def save_strategy_state(states: dict[str, StrategyState], state_dir: Path | None = None):
    """
    Save strategy state to disk.

    Args:
        states: Dictionary mapping strategy name to StrategyState
        state_dir: Directory for state files (defaults to repo_root/state)
    """
    if state_dir is None:
        # Default to repo_root/state
        import os

        env_path = os.getenv("AI_TRADER_STRATEGY_STATE_DIR")
        if env_path:
            state_dir = Path(env_path)
        else:
            repo_root = Path(__file__).resolve().parents[2]
            state_dir = repo_root / "state"

    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    state_file = state_dir / "strategy_state.json"

    try:
        # Convert to JSON-serializable format
        data = {}
        for name, state in states.items():
            data[name] = state.model_dump()

        # Write atomically via temp file
        temp_file = state_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump(data, f, indent=2)

        # Atomic rename
        temp_file.replace(state_file)

    except Exception:
        pass  # Fail silently to avoid breaking runs


def initialize_strategy_states(
    states: dict[str, StrategyState], strategy_names: list[str]
) -> dict[str, StrategyState]:
    """
    Initialize strategies with equal weights if they don't exist.

    Args:
        states: Existing states dictionary
        strategy_names: List of strategy names

    Returns:
        Updated states dictionary
    """
    if not strategy_names:
        return states

    equal_weight = 1.0 / len(strategy_names)

    for name in strategy_names:
        if name not in states:
            states[name] = StrategyState(name=name, weight=equal_weight)

    return states


def print_strategy_state_summary(states: dict[str, StrategyState]):
    """
    Print summary of strategy states.

    Args:
        states: Dictionary of strategy states
    """
    if not states:
        print("\nNo strategy state available")
        return

    print("\n" + "=" * 80)
    print("Strategy Performance Summary")
    print("=" * 80)
    print(
        f"{'Strategy':<20} {'Weight':>8} {'PnL':>10} {'Samples':>8} "
        f"{'Mean%':>8} {'Std%':>8} {'DD%':>8}"
    )
    print("-" * 80)

    for name, state in sorted(states.items()):
        mean_ret = 0.0
        std_ret = 0.0

        if state.rolling_returns:
            mean_ret = sum(state.rolling_returns) / len(state.rolling_returns) * 100
            if len(state.rolling_returns) > 1:
                variance = sum((r - mean_ret / 100) ** 2 for r in state.rolling_returns) / (
                    len(state.rolling_returns) - 1
                )
                std_ret = variance**0.5 * 100

        print(
            f"{name:<20} {state.weight:>8.3f} {state.cumulative_pnl:>10.2f} "
            f"{len(state.rolling_returns):>8} {mean_ret:>8.2f} {std_ret:>8.2f} "
            f"{state.drawdown * 100:>8.2f}"
        )

    print("=" * 80)
