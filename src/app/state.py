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
# Strategy State Management (for performance tracking and dynamic weights)
# ============================================================================


class StrategyState(BaseModel):
    """
    Per-strategy performance state for dynamic weight allocation.

    Tracks performance metrics and capital allocation weight for each strategy.
    Used by Shadow PnL performance tracking to adjust weights based on returns.
    """

    name: str = Field(description="Strategy identifier (e.g., 'Trend_MA20')")
    weight: float = Field(default=1.0, description="Capital allocation weight (0.0-1.0)")
    cumulative_pnl: float = Field(default=0.0, description="Total profit/loss from attributed returns")
    rolling_returns: list[float] = Field(
        default_factory=list, description="Rolling window of return samples (max 200)"
    )
    drawdown: float = Field(default=0.0, description="Maximum decline from peak equity (negative)")
    trade_count: int = Field(default=0, description="Number of attributed samples")
    last_updated: str = Field(
        default="", description="ISO timestamp of last performance update"
    )


def load_strategy_state(state_dir: str = "state") -> dict[str, StrategyState]:
    """
    Load strategy states from state directory.

    Args:
        state_dir: Directory containing strategy_state.json (default: "state")

    Returns:
        Dict mapping strategy name -> StrategyState
    """
    state_file = Path(state_dir) / "strategy_state.json"

    if not state_file.exists():
        return {}

    try:
        with open(state_file) as f:
            data = json.load(f)
            return {name: StrategyState(**state_data) for name, state_data in data.items()}
    except Exception as e:
        import logging

        logger = logging.getLogger("ai-trader")
        logger.warning(f"Failed to load strategy state from {state_file}: {e}")
        return {}


def save_strategy_state(states: dict[str, StrategyState], state_dir: str = "state"):
    """
    Save strategy states to state directory.

    Args:
        states: Dict of StrategyState objects to save
        state_dir: Directory to save strategy_state.json (default: "state")
    """
    state_path = Path(state_dir)
    state_path.mkdir(exist_ok=True)

    state_file = state_path / "strategy_state.json"

    # Convert to dict
    data = {name: state.model_dump() for name, state in states.items()}

    with open(state_file, "w") as f:
        json.dump(data, f, indent=2)


def initialize_strategy_states(
    states: dict[str, StrategyState], strategy_names: list[str]
) -> dict[str, StrategyState]:
    """
    Initialize strategy states with equal weights.

    Creates new StrategyState objects for strategies not already in states.
    Assigns equal weight to all strategies (1.0 / num_strategies).

    Args:
        states: Existing strategy states (may be empty)
        strategy_names: List of strategy names to initialize

    Returns:
        Updated dict of strategy states with equal weights
    """
    num_strategies = len(strategy_names)
    equal_weight = 1.0 / num_strategies if num_strategies > 0 else 1.0

    for name in strategy_names:
        if name not in states:
            # Create new state with equal weight
            states[name] = StrategyState(
                name=name,
                weight=equal_weight,
                cumulative_pnl=0.0,
                rolling_returns=[],
                drawdown=0.0,
                trade_count=0,
                last_updated=datetime.now(ZoneInfo("UTC")).isoformat(),
            )
        else:
            # Update existing state's weight to equal (resets on each run before weight update)
            states[name].weight = equal_weight

    return states


def update_strategy_weights(
    states: dict[str, StrategyState],
    min_samples: int = 20,
    smoothing: float = 0.9,
    min_weight: float = 0.05,
    max_weight: float = 0.80,
) -> dict[str, StrategyState]:
    """
    Update strategy weights based on performance scores.

    Conservative algorithm:
    1. Require ALL strategies have >= min_samples before adjusting weights
    2. Score = mean(returns) - 0.5*stdev(returns) - abs(drawdown)
    3. Softmax normalization to convert scores to target weights
    4. Smooth: new_weight = smoothing*old_weight + (1-smoothing)*target_weight
    5. Clamp to [min_weight, max_weight]
    6. Normalize to sum=1.0

    Args:
        states: Dict of StrategyState objects
        min_samples: Minimum samples required before weight updates (default 20)
        smoothing: Smoothing factor for weight updates (default 0.9, higher = more conservative)
        min_weight: Minimum weight per strategy (default 0.05 = 5%)
        max_weight: Maximum weight per strategy (default 0.80 = 80%)

    Returns:
        Updated dict of strategy states with new weights
    """
    import math

    # Check if ALL strategies have sufficient samples
    all_ready = all(len(s.rolling_returns) >= min_samples for s in states.values())

    if not all_ready:
        # Keep equal weights until all strategies have enough samples
        num_strategies = len(states)
        equal_weight = 1.0 / num_strategies if num_strategies > 0 else 1.0

        for state in states.values():
            state.weight = equal_weight

        return states

    # Compute performance scores
    scores = {}
    for name, state in states.items():
        if not state.rolling_returns:
            scores[name] = 0.0
            continue

        # Mean return
        mean_return = sum(state.rolling_returns) / len(state.rolling_returns)

        # Standard deviation
        variance = sum((r - mean_return) ** 2 for r in state.rolling_returns) / len(
            state.rolling_returns
        )
        std_dev = math.sqrt(variance) if variance > 0 else 0.0

        # Score = mean - 0.5*std - abs(drawdown)
        score = mean_return - 0.5 * std_dev - abs(state.drawdown)
        scores[name] = score

    # Softmax normalization (with numerical stability)
    max_score = max(scores.values()) if scores else 0.0
    exp_scores = {name: math.exp(score - max_score) for name, score in scores.items()}
    sum_exp = sum(exp_scores.values())

    target_weights = (
        {name: exp_val / sum_exp for name, exp_val in exp_scores.items()} if sum_exp > 0 else {}
    )

    # Smooth and clamp weights
    for name, state in states.items():
        if name in target_weights:
            target_weight = target_weights[name]

            # Smooth: new = smoothing*old + (1-smoothing)*target
            smoothed_weight = smoothing * state.weight + (1.0 - smoothing) * target_weight

            # Clamp to bounds
            clamped_weight = max(min_weight, min(max_weight, smoothed_weight))

            state.weight = clamped_weight

    # Normalize to sum=1.0
    total_weight = sum(s.weight for s in states.values())
    if total_weight > 0:
        for state in states.values():
            state.weight /= total_weight

    return states


def print_strategy_state_summary(states: dict[str, StrategyState], min_samples: int = 20):
    """
    Print strategy performance summary table.

    Args:
        states: Dict of StrategyState objects
        min_samples: Minimum samples required for weight updates (shown in header)
    """
    print()
    print("=" * 80)
    print(f"Strategy Performance Summary (min_samples={min_samples})")
    print("=" * 80)
    print(
        f"{'Strategy':<20} {'Weight':>10} {'Cumul PnL':>12} {'Drawdown':>10} {'Samples':>10}"
    )
    print("-" * 80)

    for state in states.values():
        weight_pct = state.weight * 100
        drawdown_pct = state.drawdown * 100

        print(
            f"{state.name:<20} {weight_pct:>9.1f}% "
            f"${state.cumulative_pnl:>11.2f} {drawdown_pct:>9.1f}% "
            f"{state.trade_count:>10}"
        )

    print("=" * 80)
