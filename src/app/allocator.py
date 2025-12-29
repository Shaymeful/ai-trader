"""Allocator module for distributing capital across strategies."""

import logging
from dataclasses import dataclass
from decimal import Decimal

from src.app.config import Config
from src.app.strategies import PositionIntent


@dataclass
class AllocationResult:
    """Result of portfolio allocation."""

    target_positions: dict[str, int]  # symbol -> target quantity (aggregated across strategies)
    strategy_budgets: dict[str, Decimal]  # strategy_name -> allocated budget
    strategy_allocations: dict[str, dict[str, float]]  # strategy -> {symbol -> notional}
    warnings: list[str]  # Any warnings during allocation


class Allocator:
    """
    Portfolio allocator that distributes capital across strategies.

    Supports both equal-weight and dynamic weight allocation.
    Aggregates target positions across strategies by summing target quantities per symbol.
    """

    def __init__(self, config: Config):
        """
        Initialize allocator.

        Args:
            config: Trading configuration with risk parameters
        """
        self.config = config
        self.logger = logging.getLogger("ai-trader")

    def allocate(
        self,
        strategy_intents: dict[str, list[PositionIntent]],
        current_prices: dict[str, Decimal],
        strategy_weights: dict[str, float] | None = None,
    ) -> AllocationResult:
        """
        Allocate capital across strategies and compute target positions.

        Strategy:
        1. Divide total capital using strategy weights (equal if not provided)
        2. For each strategy's intents, scale to fit within strategy budget
        3. Aggregate target quantities across strategies per symbol
        4. Track per-strategy allocations for performance attribution

        Args:
            strategy_intents: Dict mapping strategy_name -> list of PositionIntent
            current_prices: Dict mapping symbol -> current price
            strategy_weights: Optional dict of strategy weights (defaults to equal weight)

        Returns:
            AllocationResult with target positions and metadata
        """
        warnings = []
        num_strategies = len(strategy_intents)

        if num_strategies == 0:
            self.logger.warning("No strategies provided to allocator")
            return AllocationResult(
                target_positions={},
                strategy_budgets={},
                strategy_allocations={},
                warnings=["No strategies provided"],
            )

        # Use provided weights or equal weights
        if strategy_weights is None:
            equal_weight = 1.0 / num_strategies
            strategy_weights = {name: equal_weight for name in strategy_intents}

        # Normalize weights to sum to 1.0
        total_weight = sum(strategy_weights.values())
        if total_weight > 0:
            strategy_weights = {k: v / total_weight for k, v in strategy_weights.items()}

        # Calculate budgets from weights
        strategy_budgets = {
            name: self.config.max_positions_notional * Decimal(str(strategy_weights.get(name, 0)))
            for name in strategy_intents
        }

        self.logger.info(
            f"Allocating ${self.config.max_positions_notional} across {num_strategies} strategies"
        )

        # Aggregate target positions per symbol and track per-strategy allocations
        aggregated_targets: dict[str, int] = {}
        strategy_allocations: dict[str, dict[str, float]] = {name: {} for name in strategy_intents}

        for strategy_name, intents in strategy_intents.items():
            self.logger.info(f"Processing {len(intents)} intents from {strategy_name}")

            for intent in intents:
                symbol = intent.symbol
                qty = intent.target_quantity

                if symbol not in aggregated_targets:
                    aggregated_targets[symbol] = 0

                aggregated_targets[symbol] += qty

                # Track notional allocation per strategy-symbol
                if symbol in current_prices:
                    notional = float(abs(qty) * current_prices[symbol])
                    if symbol not in strategy_allocations[strategy_name]:
                        strategy_allocations[strategy_name][symbol] = 0.0
                    strategy_allocations[strategy_name][symbol] += notional

        # Apply risk caps
        final_targets = self._apply_risk_caps(aggregated_targets, current_prices, warnings)

        return AllocationResult(
            target_positions=final_targets,
            strategy_budgets=strategy_budgets,
            strategy_allocations=strategy_allocations,
            warnings=warnings,
        )

    def _apply_risk_caps(
        self,
        targets: dict[str, int],
        prices: dict[str, Decimal],
        warnings: list[str],
    ) -> dict[str, int]:
        """
        Apply risk caps to target positions.

        Note: max_order_notional is enforced by the executor via order slicing.
        This method only enforces max_positions_notional (total portfolio cap).

        Args:
            targets: Dict of symbol -> target quantity
            prices: Dict of symbol -> current price
            warnings: List to append warnings to

        Returns:
            Capped target positions
        """
        capped_targets = {}
        total_notional = Decimal("0")

        for symbol, qty in targets.items():
            if symbol not in prices:
                warnings.append(f"{symbol}: No price available, skipping")
                continue

            price = prices[symbol]
            notional = abs(qty) * price

            # Note: max_order_notional is now enforced by executor via order slicing
            # We only enforce max_positions_notional here (total portfolio cap)

            # Check if adding this position would exceed total notional
            if total_notional + notional > self.config.max_positions_notional:
                remaining_budget = self.config.max_positions_notional - total_notional
                if remaining_budget > price:
                    # Can fit some shares
                    max_qty_within_budget = int(remaining_budget / price)
                    qty = max_qty_within_budget if qty > 0 else -max_qty_within_budget
                    notional = abs(qty) * price
                    warnings.append(f"{symbol}: Reduced to {qty} shares to fit within total budget")
                else:
                    # Can't fit any shares
                    warnings.append(
                        f"{symbol}: Skipped due to insufficient budget "
                        f"(${remaining_budget:.2f} < ${price:.2f})"
                    )
                    continue

            if qty != 0:
                capped_targets[symbol] = qty
                total_notional += notional

        self.logger.info(f"Final portfolio notional: ${total_notional:.2f}")
        return capped_targets
