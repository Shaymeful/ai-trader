"""Strategy performance tracking and attribution."""

import math
from decimal import Decimal

from src.app.state import StrategyState


class PerformanceTracker:
    """Tracks strategy performance and attributes returns."""

    def __init__(self):
        """Initialize performance tracker."""
        self.prev_prices: dict[str, float] = {}

    def update_strategy_performance(
        self,
        states: dict[str, StrategyState],
        strategy_allocations: dict[str, dict[str, float]],  # strategy -> {symbol -> notional}
        current_prices: dict[str, Decimal],
        prev_prices: dict[str, Decimal] | None = None,
    ):
        """
        Update strategy performance based on mark-to-market returns.

        Uses simple 1-step return calculation:
        - return = (price_t - price_t-1) / price_t-1
        - attribute return * allocated notional to each strategy

        Args:
            states: Dictionary of strategy states to update
            strategy_allocations: Dict mapping strategy -> {symbol -> notional allocated}
            current_prices: Current prices for symbols
            prev_prices: Previous prices (if None, uses stored prev_prices)
        """
        if prev_prices is None:
            prev_prices_dict = self.prev_prices
        else:
            prev_prices_dict = {k: float(v) for k, v in prev_prices.items()}

        # Store current prices for next iteration
        self.prev_prices = {k: float(v) for k, v in current_prices.items()}

        # If no previous prices, skip this update
        if not prev_prices_dict:
            return

        # Calculate returns for each symbol
        symbol_returns: dict[str, float] = {}
        for symbol, current_price in current_prices.items():
            if symbol in prev_prices_dict:
                prev_price = prev_prices_dict[symbol]
                if prev_price > 0:
                    symbol_returns[symbol] = (float(current_price) - prev_price) / prev_price

        # Attribute returns to strategies
        for strategy_name, allocations in strategy_allocations.items():
            if strategy_name not in states:
                continue

            state = states[strategy_name]
            strategy_pnl = 0.0
            total_notional = sum(allocations.values())

            if total_notional == 0:
                continue

            # Calculate weighted return for this strategy
            weighted_return = 0.0
            for symbol, notional in allocations.items():
                if symbol in symbol_returns:
                    # Weight symbol return by notional allocation
                    weight = notional / total_notional
                    weighted_return += symbol_returns[symbol] * weight
                    strategy_pnl += symbol_returns[symbol] * notional

            # Update strategy state
            state.add_return(weighted_return)
            state.cumulative_pnl += strategy_pnl
            state.trade_count += 1
            state.update_drawdown()


def update_strategy_weights(
    states: dict[str, StrategyState],
    min_samples: int = 20,
    drawdown_threshold: float = -0.02,  # -2%
    smoothing: float = 0.9,  # 90% old weight, 10% new weight
    min_weight: float = 0.05,
    max_weight: float = 0.80,
) -> dict[str, StrategyState]:
    """
    Update strategy weights based on performance.

    Conservative rules:
    - Requires min_samples before adjusting weights
    - Score = mean(returns) - 0.5*stdev(returns) - drawdown_penalty
    - Softmax to convert scores to target weights
    - Smooth transition: new_w = smoothing*old_w + (1-smoothing)*target_w
    - Enforce min/max bounds

    Args:
        states: Dictionary of strategy states
        min_samples: Minimum samples required to adjust weights
        drawdown_threshold: Drawdown threshold to clamp weights
        smoothing: Weight smoothing factor (0=immediate, 1=no change)
        min_weight: Minimum allowed weight
        max_weight: Maximum allowed weight

    Returns:
        Updated states dictionary
    """
    if not states:
        return states

    # Calculate scores for each strategy
    scores: dict[str, float] = {}
    for name, state in states.items():
        # Require minimum samples
        if len(state.rolling_returns) < min_samples:
            # Keep equal weight for new strategies
            scores[name] = 1.0
            continue

        # Calculate mean and std of returns
        returns = state.rolling_returns
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        std_return = math.sqrt(variance) if variance > 0 else 0.0

        # Calculate score: mean - 0.5*std - drawdown_penalty
        drawdown_penalty = abs(state.drawdown) if state.drawdown < 0 else 0.0
        score = mean_return - 0.5 * std_return - drawdown_penalty

        # Clamp weight down if drawdown exceeds threshold
        if state.drawdown < drawdown_threshold:
            score = min(score, -1.0)  # Force low score

        scores[name] = score

    # Convert scores to target weights using softmax (with offset for numerical stability)
    max_score = max(scores.values()) if scores else 0.0
    exp_scores = {name: math.exp(score - max_score) for name, score in scores.items()}
    total_exp = sum(exp_scores.values())

    target_weights = {}
    if total_exp > 0:
        target_weights = {name: exp_score / total_exp for name, exp_score in exp_scores.items()}
    else:
        # Fallback to equal weights
        equal_weight = 1.0 / len(states)
        target_weights = {name: equal_weight for name in states}

    # Apply smoothing and bounds
    for name, state in states.items():
        if name not in target_weights:
            continue

        target_w = target_weights[name]

        # Smooth transition
        new_w = smoothing * state.weight + (1.0 - smoothing) * target_w

        # Enforce bounds
        new_w = max(min_weight, min(max_weight, new_w))

        state.weight = new_w

    # Normalize weights to sum to 1.0
    total_weight = sum(state.weight for state in states.values())
    if total_weight > 0:
        for state in states.values():
            state.weight /= total_weight

    return states
