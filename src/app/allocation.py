"""Centralized equity-based allocation and position sizing engine.

This module provides deterministic functions for:
1. Computing normalized strategy weights based on enabled strategies
2. Allocating account equity across strategies
3. Sizing positions from intents using confidence and risk limits
4. Converting notional targets to share quantities (fractional or whole)

Key Design Principles:
- Use account equity (not buying_power) as allocation base
- Normalize weights dynamically among enabled strategies
- Support fractional shares where allowed
- Deterministic: same inputs always produce same outputs
- No side effects: all functions are pure

Weight Normalization:
When strategies are enabled/disabled, weights are normalized so the sum = 1.0:
    normalized_weight_i = weight_i / sum(weights of enabled strategies)

Example:
    Strategy A: weight=0.5, enabled=True
    Strategy B: weight=0.3, enabled=True
    Strategy C: weight=0.2, enabled=False

    Sum of enabled weights = 0.5 + 0.3 = 0.8
    Normalized A = 0.5 / 0.8 = 0.625 (62.5% of capital)
    Normalized B = 0.3 / 0.8 = 0.375 (37.5% of capital)
"""

import logging
from decimal import Decimal

logger = logging.getLogger("ai-trader")


def get_total_equity(account_state: dict | None) -> float | None:
    """
    Extract total equity from account state.

    Account equity is used as the allocation base (not buying_power) because
    it represents the true account value for risk management purposes.

    Args:
        account_state: Account state dictionary from broker (e.g., Alpaca's get_account())
                      Expected to have 'equity' field

    Returns:
        Total equity as float, or None if unavailable

    Example:
        >>> account = {"equity": "50000.00", "buying_power": "100000.00"}
        >>> get_total_equity(account)
        50000.0
    """
    if account_state is None:
        logger.warning("Account state is None - cannot get equity")
        return None

    equity_value = account_state.get("equity")
    if equity_value is None:
        logger.warning("Account state missing 'equity' field")
        return None

    try:
        # Convert to float (handle string or numeric types)
        return float(equity_value)
    except (ValueError, TypeError) as e:
        logger.error(f"Failed to convert equity to float: {equity_value} - {e}")
        return None


def compute_weight_summary(strategies: list) -> dict:
    """
    Compute normalized weights for enabled strategies.

    Normalization ensures weights sum to 1.0 across enabled strategies,
    preventing allocation errors when strategies are added/removed/disabled.

    Args:
        strategies: List of StrategyConfig objects with 'enabled' and 'weight' fields

    Returns:
        Dictionary with:
        - enabled_ids: List of enabled strategy IDs
        - sum_enabled_weights: Sum of configured weights for enabled strategies
        - normalized_weights: Dict mapping strategy_id -> normalized weight (sum=1.0)
        - configured_weights: Dict mapping strategy_id -> original configured weight

    Example:
        >>> strategies = [
        ...     StrategyConfig(strategy_id="A", enabled=True, weight=0.5),
        ...     StrategyConfig(strategy_id="B", enabled=True, weight=0.3),
        ...     StrategyConfig(strategy_id="C", enabled=False, weight=0.2),
        ... ]
        >>> result = compute_weight_summary(strategies)
        >>> result["normalized_weights"]["A"]
        0.625  # 0.5 / (0.5 + 0.3)
    """
    enabled_strategies = [s for s in strategies if s.enabled]

    if not enabled_strategies:
        logger.warning("No enabled strategies - returning empty weight summary")
        return {
            "enabled_ids": [],
            "sum_enabled_weights": 0.0,
            "normalized_weights": {},
            "configured_weights": {},
        }

    # Sum of configured weights for enabled strategies
    sum_enabled_weights = sum(s.weight for s in enabled_strategies)

    # Build configured weights map (for audit/display)
    configured_weights = {s.strategy_id: s.weight for s in strategies}

    # Normalize weights
    if sum_enabled_weights == 0:
        # Edge case: all enabled strategies have weight=0
        # Assign equal weight to each
        logger.warning(
            f"Sum of enabled weights is 0 - assigning equal weight to {len(enabled_strategies)} strategies"
        )
        equal_weight = 1.0 / len(enabled_strategies)
        normalized_weights = {s.strategy_id: equal_weight for s in enabled_strategies}
    else:
        # Normal case: normalize by sum
        normalized_weights = {
            s.strategy_id: s.weight / sum_enabled_weights for s in enabled_strategies
        }

    return {
        "enabled_ids": [s.strategy_id for s in enabled_strategies],
        "sum_enabled_weights": sum_enabled_weights,
        "normalized_weights": normalized_weights,
        "configured_weights": configured_weights,
    }


def compute_strategy_budget(equity: float, normalized_weight: float) -> float:
    """
    Compute strategy's capital budget from equity and normalized weight.

    This determines how much capital (in dollars) a strategy can allocate
    across all its positions.

    Args:
        equity: Total account equity (dollars)
        normalized_weight: Strategy's normalized allocation weight (0.0 to 1.0)

    Returns:
        Strategy budget in dollars

    Example:
        >>> compute_strategy_budget(50000.0, 0.625)
        31250.0  # 62.5% of $50k
    """
    if equity < 0:
        logger.warning(f"Negative equity: {equity} - using 0")
        equity = 0

    if not 0 <= normalized_weight <= 1.0:
        logger.warning(f"Normalized weight {normalized_weight} outside [0,1] - clamping")
        normalized_weight = max(0.0, min(1.0, normalized_weight))

    return equity * normalized_weight


def compute_target_notional(
    strategy_budget: float, conviction: float, risk_limits: dict | None = None
) -> float:
    """
    Compute target notional (dollar value) for a position based on conviction.

    Uses conviction to scale position size within the strategy's budget,
    respecting any max_position_size risk limit.

    Args:
        strategy_budget: Total capital allocated to strategy (dollars)
        conviction: Signal strength/confidence (0.0 to 1.0)
        risk_limits: Optional dict with 'max_position_size' (dollars per position)

    Returns:
        Target notional in dollars

    Example:
        >>> compute_target_notional(31250.0, 0.85, {"max_position_size": 5000})
        5000.0  # Min of (31250 * 0.85, 5000) = 5000
    """
    if strategy_budget < 0:
        logger.warning(f"Negative budget: {strategy_budget} - using 0")
        strategy_budget = 0

    if not 0 <= conviction <= 1.0:
        logger.warning(f"Conviction {conviction} outside [0,1] - clamping")
        conviction = max(0.0, min(1.0, conviction))

    # Base notional from conviction
    base_notional = strategy_budget * conviction

    # Apply max position size limit if specified
    if risk_limits and "max_position_size" in risk_limits:
        max_position_size = float(risk_limits["max_position_size"])
        if max_position_size > 0:
            return min(base_notional, max_position_size)

    return base_notional


def compute_qty_from_notional(
    price: float | Decimal,
    notional: float,
    allow_fractional: bool = True,
    min_qty: int = 0,
) -> int | float:
    """
    Convert notional dollar amount to share quantity.

    Supports both fractional and whole-share rounding based on broker capabilities.

    Args:
        price: Current price per share (dollars)
        notional: Target dollar amount to allocate
        allow_fractional: If True, return fractional shares; if False, floor to whole shares
        min_qty: Minimum quantity (default 0, typically 1 for whole shares)

    Returns:
        Share quantity (int if allow_fractional=False, float if allow_fractional=True)

    Example:
        >>> compute_qty_from_notional(150.0, 5000.0, allow_fractional=True)
        33.333333333333336

        >>> compute_qty_from_notional(150.0, 5000.0, allow_fractional=False)
        33
    """
    # Convert price to float if Decimal
    price_float = float(price)

    if price_float <= 0:
        logger.warning(f"Invalid price: {price_float} - returning min_qty")
        return min_qty

    if notional < 0:
        logger.warning(f"Negative notional: {notional} - using 0")
        notional = 0

    # Calculate raw quantity
    qty_raw = notional / price_float

    # Round based on fractional support
    if allow_fractional:
        # Return fractional quantity
        return max(qty_raw, min_qty)
    else:
        # Floor to whole shares
        qty_int = int(qty_raw)
        return max(qty_int, min_qty)


def net_intents_by_symbol(
    intents: list, market_data: dict, strategy_map: dict | None = None
) -> dict:
    """
    Net multiple strategy intents for the same symbol into single target.

    Netting Policy:
    - Convert each intent to notional using current market price
    - target_quantity > 0 → +notional (buy/long)
    - target_quantity < 0 → -notional (sell/short)
    - target_quantity == 0 → neutral (close position)
    - Sum notionals by symbol across all strategies
    - If net > 0: net BUY intent
    - If net < 0: net SELL intent
    - If net == 0: no action (intents cancel out)

    This allows multiple strategies to have conflicting opinions on the same symbol,
    producing a deterministic net position based on conviction-weighted quantities.

    Args:
        intents: List of PositionIntent objects with symbol, target_quantity, conviction
        market_data: Dict mapping symbol -> {"price": float} (current market price)
        strategy_map: Optional dict mapping intent object -> strategy_id (for attribution)

    Returns:
        Dict mapping symbol -> dict with:
        - net_notional: Net dollar amount (+ for buy, - for sell)
        - net_quantity: Net share quantity (computed from net_notional)
        - contributing_intents: List of dicts with {strategy_id, intent, notional, quantity}
        - final_direction: "buy", "sell", or "neutral"

    Example:
        >>> intents = [
        ...     PositionIntent("AAPL", 10, 0.8, "Strong momentum"),  # wants 10 shares
        ...     PositionIntent("AAPL", -5, 0.6, "Risk reduction"),   # wants -5 shares
        ... ]
        >>> market_data = {"AAPL": {"price": 150.0}}
        >>> net_intents_by_symbol(intents, market_data)
        {
            "AAPL": {
                "net_notional": 750.0,  # (10 * 150) + (-5 * 150) = 750
                "net_quantity": 5,       # Net wants 5 shares long
                "contributing_intents": [...],
                "final_direction": "buy"
            }
        }
    """
    # Group intents by symbol
    symbol_groups = {}
    for intent in intents:
        if intent.symbol not in symbol_groups:
            symbol_groups[intent.symbol] = []
        symbol_groups[intent.symbol].append(intent)

    # Process each symbol
    netted_results = {}

    for symbol, symbol_intents in symbol_groups.items():
        # Get current price for this symbol
        price_data = market_data.get(symbol)
        if price_data is None:
            logger.warning(f"No market data for {symbol} - skipping netting for this symbol")
            continue

        price = price_data.get("price")
        if price is None or price <= 0:
            logger.warning(
                f"Invalid price for {symbol}: {price} - skipping netting for this symbol"
            )
            continue

        # Convert each intent to notional and track contributions
        contributing_intents = []
        net_notional = 0.0

        for intent in symbol_intents:
            # Compute signed notional: qty * price
            # Positive qty → positive notional (buy)
            # Negative qty → negative notional (sell)
            intent_notional = intent.target_quantity * price

            # Get strategy ID for attribution (using id() since intent is not hashable)
            strategy_id = strategy_map.get(id(intent)) if strategy_map else None

            contributing_intents.append(
                {
                    "strategy_id": strategy_id,
                    "intent": intent,
                    "notional": intent_notional,
                    "quantity": intent.target_quantity,
                }
            )

            net_notional += intent_notional

        # Determine final direction
        if net_notional > 0:
            final_direction = "buy"
        elif net_notional < 0:
            final_direction = "sell"
        else:
            final_direction = "neutral"

        # Compute net quantity (for reference - final sizing will use notional)
        net_quantity = net_notional / price if price > 0 else 0

        netted_results[symbol] = {
            "net_notional": net_notional,
            "net_quantity": net_quantity,
            "contributing_intents": contributing_intents,
            "final_direction": final_direction,
            "price": price,  # Store price used for reference
        }

    return netted_results


def scale_notionals_for_target_utilization(
    netted_results: dict,
    equity: float,
    current_exposure: float,
    target_exposure_pct: float,
    max_positions: int,
    current_positions: int,
    min_order_notional: float = 500,
    per_position_max_pct: float = 0.15,
) -> dict:
    """
    Scale netted notionals to move portfolio toward target utilization.

    Strategy:
    1. Compute remaining_budget = (target_exposure_pct × equity) - current_exposure
    2. Compute sum of all buy notionals from netted results
    3. Scale factor = remaining_budget / sum_buy_notionals (capped at 1.0 to prevent over-allocation)
    4. Apply scale factor to all buy notionals
    5. Cap each position at per_position_max_pct × equity
    6. Filter out orders below min_order_notional

    This ensures we size orders to fill available capital up to the target exposure cap.

    Args:
        netted_results: Dict from net_intents_by_symbol (symbol -> net_notional, etc.)
        equity: Account equity
        current_exposure: Current portfolio exposure (sum of position values)
        target_exposure_pct: Target exposure as decimal (e.g., 0.60 for 60%)
        max_positions: Maximum number of concurrent positions
        current_positions: Number of open positions
        min_order_notional: Minimum notional per order (skip smaller orders)
        per_position_max_pct: Maximum per-position as decimal (e.g., 0.15 for 15%)

    Returns:
        Dict mapping symbol -> scaled net_notional (same structure as netted_results)
    """
    if not netted_results:
        logger.info("No netted results to scale")
        return netted_results

    # Compute target metrics
    target_exposure = equity * target_exposure_pct
    remaining_budget = target_exposure - current_exposure
    slots_available = max_positions - current_positions

    logger.info(
        f"Target Utilization Scaling: equity=${equity:.2f}, "
        f"current_exposure=${current_exposure:.2f} ({current_exposure/equity*100:.1f}%), "
        f"target_exposure=${target_exposure:.2f} ({target_exposure_pct*100:.1f}%), "
        f"remaining_budget=${remaining_budget:.2f}, "
        f"slots_available={slots_available}"
    )

    # If no budget or no slots, return empty (block all orders)
    if remaining_budget <= 0:
        logger.warning("Target exposure reached or exceeded - blocking all new orders")
        return {}

    if slots_available <= 0:
        logger.warning("Max positions reached - blocking all new orders")
        return {}

    # Sum buy notionals (only scale buys, not sells)
    buy_symbols = [s for s, data in netted_results.items() if data["net_notional"] > 0]
    sum_buy_notionals = sum(netted_results[s]["net_notional"] for s in buy_symbols)

    if sum_buy_notionals == 0:
        logger.info("No buy intents to scale")
        return netted_results  # Keep sells as-is

    # Compute scale factor to fit remaining budget
    scale_factor = remaining_budget / sum_buy_notionals
    # Cap at 1.0 to prevent over-scaling (never size larger than strategy requested)
    scale_factor = min(scale_factor, 1.0)

    # Also limit by available slots - distribute budget evenly across slots
    per_slot_notional = remaining_budget / slots_available
    per_position_max_notional = equity * per_position_max_pct

    logger.info(
        f"Scaling strategy: sum_buy_notionals=${sum_buy_notionals:.2f}, "
        f"scale_factor={scale_factor:.3f}, per_slot=${per_slot_notional:.2f}, "
        f"per_position_max=${per_position_max_notional:.2f}"
    )

    # Scale and cap each symbol
    scaled_results = {}
    orders_filtered_count = 0

    for symbol, data in netted_results.items():
        original_notional = data["net_notional"]

        # Only scale buys; keep sells as-is
        if original_notional > 0:
            scaled_notional = original_notional * scale_factor
            # Cap at per-position max
            scaled_notional = min(scaled_notional, per_position_max_notional)

            # Filter out tiny orders
            if scaled_notional < min_order_notional:
                logger.info(
                    f"{symbol}: Filtered out (scaled_notional=${scaled_notional:.2f} < min=${min_order_notional})"
                )
                orders_filtered_count += 1
                continue

            # Recompute net_quantity from scaled notional
            price = data["price"]
            scaled_quantity = scaled_notional / price if price > 0 else 0

            # Create scaled result
            scaled_results[symbol] = {
                **data,
                "net_notional": scaled_notional,
                "net_quantity": scaled_quantity,
                "original_notional": original_notional,
                "scale_factor": scale_factor,
            }

            logger.info(
                f"{symbol}: scaled from ${original_notional:.2f} to ${scaled_notional:.2f} "
                f"(qty: {data['net_quantity']:.2f} → {scaled_quantity:.2f})"
            )
        else:
            # Keep sells unchanged
            scaled_results[symbol] = data

    logger.info(
        f"Scaled {len(buy_symbols)} buy intents, "
        f"filtered {orders_filtered_count} below min_order_notional, "
        f"final: {len([s for s in scaled_results if scaled_results[s]['net_notional'] > 0])} buys"
    )

    return scaled_results
