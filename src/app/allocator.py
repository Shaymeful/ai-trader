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
    warnings: list[str]  # Any warnings during allocation


class Allocator:
    """
    Portfolio allocator that distributes capital across strategies.

    Uses equal-weight allocation: each strategy gets an equal share of total capital.
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
    ) -> AllocationResult:
        """
        Allocate capital across strategies and compute target positions.

        Strategy:
        1. Divide total capital (max_positions_notional) equally among strategies
        2. For each strategy's intents, scale to fit within strategy budget
        3. Aggregate target quantities across strategies per symbol
        4. Apply risk caps (max_order_notional, max_positions_notional)

        Args:
            strategy_intents: Dict mapping strategy_name -> list of PositionIntent
            current_prices: Dict mapping symbol -> current price

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
                warnings=["No strategies provided"],
            )

        # Equal-weight allocation: divide total capital by number of strategies
        budget_per_strategy = self.config.max_positions_notional / num_strategies
        strategy_budgets = {name: budget_per_strategy for name in strategy_intents}

        self.logger.info(
            f"Allocating ${self.config.max_positions_notional} across {num_strategies} strategies"
        )
        self.logger.info(f"Per-strategy budget: ${budget_per_strategy}")

        # Aggregate target positions per symbol
        # Simple approach: sum target quantities across strategies
        aggregated_targets: dict[str, int] = {}

        for strategy_name, intents in strategy_intents.items():
            self.logger.info(f"Processing {len(intents)} intents from {strategy_name}")

            for intent in intents:
                symbol = intent.symbol
                qty = intent.target_quantity

                # Simple approach: start with min(1 share) unless intent says 0
                # For now, use the strategy's target quantity directly
                # (More sophisticated sizing would consider conviction, risk, etc.)
                if symbol not in aggregated_targets:
                    aggregated_targets[symbol] = 0

                aggregated_targets[symbol] += qty

        # Apply risk caps
        final_targets = self._apply_risk_caps(aggregated_targets, current_prices, warnings)

        return AllocationResult(
            target_positions=final_targets,
            strategy_budgets=strategy_budgets,
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
