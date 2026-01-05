"""Allocator module for distributing capital across strategies."""

import logging
from dataclasses import dataclass
from decimal import Decimal

from src.app import allocation
from src.app.config import Config
from src.app.strategies import PositionIntent


@dataclass
class AllocationResult:
    """Result of portfolio allocation."""

    target_positions: dict[str, int]  # symbol -> target quantity (aggregated across strategies)
    strategy_budgets: dict[str, Decimal]  # strategy_name -> allocated budget
    warnings: list[str]  # Any warnings during allocation
    weight_summary: dict | None = None  # Weight normalization summary (if using registry)
    equity_used: float | None = None  # Account equity used for allocation (if available)


class Allocator:
    """
    Portfolio allocator that distributes capital across strategies.

    Supports two allocation modes:
    1. Registry mode (NEW): Uses StrategyRegistry with equity-based normalized weights
    2. Legacy mode: Uses equal-weight allocation with max_positions_notional

    Registry mode features:
    - Uses account equity (not buying_power) as allocation base
    - Normalizes weights dynamically among enabled strategies
    - Sizes positions based on conviction and per-strategy risk limits
    - Nets multi-strategy intents by symbol

    Legacy mode (backward compatible):
    - Equal-weight allocation: each strategy gets an equal share
    - Uses max_positions_notional from config
    - Simple aggregation by summing target quantities
    """

    def __init__(self, config: Config, registry=None, broker=None, ledger=None):
        """
        Initialize allocator.

        Args:
            config: Trading configuration with risk parameters
            registry: Optional StrategyRegistry for equity-based allocation
            broker: Optional broker instance for fetching account equity
            ledger: Optional Ledger instance for emitting allocation events
        """
        self.config = config
        self.registry = registry
        self.broker = broker
        self.ledger = ledger
        self.logger = logging.getLogger("ai-trader")

    def allocate(
        self,
        strategy_intents: dict[str, list[PositionIntent]],
        current_prices: dict[str, Decimal],
    ) -> AllocationResult:
        """
        Allocate capital across strategies and compute target positions.

        Supports two modes:
        1. Registry mode (if registry + broker provided): Equity-based with normalized weights
        2. Legacy mode: Equal-weight with max_positions_notional

        Registry Mode Strategy:
        1. Fetch account equity from broker
        2. Compute normalized weights from enabled strategies in registry
        3. Allocate equity to strategies based on normalized weights
        4. Size each intent using conviction and per-strategy risk limits
        5. Net multi-strategy intents by symbol (sum notionals)
        6. Apply global risk caps

        Legacy Mode Strategy:
        1. Divide total capital (max_positions_notional) equally among strategies
        2. Aggregate target quantities across strategies per symbol (simple sum)
        3. Apply risk caps (max_order_notional, max_positions_notional)

        Args:
            strategy_intents: Dict mapping strategy_name -> list of PositionIntent
            current_prices: Dict mapping symbol -> current price

        Returns:
            AllocationResult with target positions and metadata
        """
        # Check if we should use new registry-based allocation
        if self.registry is not None and self.broker is not None:
            return self._allocate_with_registry(strategy_intents, current_prices)
        else:
            # Fall back to legacy equal-weight allocation
            return self._allocate_legacy(strategy_intents, current_prices)

    def _allocate_with_registry(
        self,
        strategy_intents: dict[str, list[PositionIntent]],
        current_prices: dict[str, Decimal],
    ) -> AllocationResult:
        """
        Allocate using registry-based equity and normalized weights (NEW MODE).

        Args:
            strategy_intents: Dict mapping strategy_name -> list of PositionIntent
            current_prices: Dict mapping symbol -> current price

        Returns:
            AllocationResult with equity-based allocation
        """
        warnings = []

        # 1. Get account equity
        try:
            account_state = self.broker.client.get_account()
            account_dict = {"equity": str(account_state.equity)}
            equity = allocation.get_total_equity(account_dict)
        except Exception as e:
            self.logger.error(f"Failed to fetch account equity: {e}")
            warnings.append(f"Failed to fetch equity: {e} - falling back to legacy mode")
            return self._allocate_legacy(strategy_intents, current_prices)

        if equity is None or equity <= 0:
            self.logger.warning("Account equity unavailable or zero - falling back to legacy mode")
            warnings.append("Equity unavailable - using legacy allocation")

            # Emit warning event
            if self.ledger:
                from src.app.ledger import WarningEquityUnavailableEvent

                self.ledger.append(
                    WarningEquityUnavailableEvent(
                        reason="Account equity unavailable or zero",
                        fallback_mode="legacy_equal_weight",
                    )
                )

            return self._allocate_legacy(strategy_intents, current_prices)

        self.logger.info(f"Account equity: ${equity:.2f}")

        # 2. Get enabled strategies from registry and compute normalized weights
        enabled_strategies = self.registry.get_enabled_strategies()
        weight_summary = allocation.compute_weight_summary(enabled_strategies)

        if not weight_summary["enabled_ids"]:
            self.logger.warning("No enabled strategies in registry")
            return AllocationResult(
                target_positions={},
                strategy_budgets={},
                warnings=["No enabled strategies in registry"],
                weight_summary=weight_summary,
                equity_used=equity,
            )

        self.logger.info(f"Enabled strategies: {weight_summary['enabled_ids']}")
        self.logger.info(f"Normalized weights: {weight_summary['normalized_weights']}")

        # Emit allocation_weights_computed event
        if self.ledger:
            from src.app.ledger import AllocationWeightsComputedEvent

            self.ledger.append(
                AllocationWeightsComputedEvent(
                    equity=equity,
                    sum_enabled_weights=weight_summary["sum_enabled_weights"],
                    normalized_weights=weight_summary["normalized_weights"],
                    configured_weights=weight_summary["configured_weights"],
                    enabled_strategy_ids=weight_summary["enabled_ids"],
                )
            )

        # 3. Compute per-strategy budgets
        strategy_budgets = {}
        for strategy_id in weight_summary["enabled_ids"]:
            normalized_weight = weight_summary["normalized_weights"][strategy_id]
            budget = allocation.compute_strategy_budget(equity, normalized_weight)
            strategy_budgets[strategy_id] = Decimal(str(budget))
            self.logger.info(
                f"{strategy_id}: budget=${budget:.2f} (weight={normalized_weight:.3f})"
            )

            # Emit strategy_budget_computed event
            if self.ledger:
                from src.app.ledger import StrategyBudgetComputedEvent

                self.ledger.append(
                    StrategyBudgetComputedEvent(
                        strategy_id=strategy_id,
                        equity=equity,
                        normalized_weight=normalized_weight,
                        budget=budget,
                    )
                )

        # 4. Flatten all intents and convert to market_data format for netting
        all_intents = []
        strategy_map = {}  # Map intent id() -> strategy_id for attribution

        for strategy_name, intents in strategy_intents.items():
            for intent in intents:
                all_intents.append(intent)
                strategy_map[id(intent)] = strategy_name

        # Convert current_prices to market_data format expected by netting function
        market_data = {symbol: {"price": float(price)} for symbol, price in current_prices.items()}

        # 5. Net intents by symbol
        if not all_intents:
            self.logger.info("No intents to allocate")
            return AllocationResult(
                target_positions={},
                strategy_budgets=strategy_budgets,
                warnings=warnings,
                weight_summary=weight_summary,
                equity_used=equity,
            )

        netted_results = allocation.net_intents_by_symbol(all_intents, market_data, strategy_map)
        self.logger.info(f"Netted {len(all_intents)} intents into {len(netted_results)} symbols")

        # 6. Convert netted notionals to target quantities
        aggregated_targets: dict[str, int] = {}
        for symbol, net_data in netted_results.items():
            net_quantity = net_data["net_quantity"]
            # Round to integer for final target (executor handles fractional if supported)
            target_qty = int(net_quantity)
            if target_qty != 0:
                aggregated_targets[symbol] = target_qty
                self.logger.info(
                    f"{symbol}: net_notional=${net_data['net_notional']:.2f}, "
                    f"target_qty={target_qty}, direction={net_data['final_direction']}"
                )

            # Emit netted_symbol_target event
            if self.ledger:
                from src.app.ledger import NettedSymbolTargetEvent

                contributing_strats = [
                    contrib["strategy_id"]
                    for contrib in net_data["contributing_intents"]
                    if contrib["strategy_id"]
                ]
                self.ledger.append(
                    NettedSymbolTargetEvent(
                        symbol=symbol,
                        net_notional=net_data["net_notional"],
                        net_quantity=net_data["net_quantity"],
                        final_direction=net_data["final_direction"],
                        contributing_strategies=contributing_strats,
                        price=net_data["price"],
                    )
                )

        # 7. Apply risk caps
        final_targets = self._apply_risk_caps(aggregated_targets, current_prices, warnings)

        return AllocationResult(
            target_positions=final_targets,
            strategy_budgets=strategy_budgets,
            warnings=warnings,
            weight_summary=weight_summary,
            equity_used=equity,
        )

    def _allocate_legacy(
        self,
        strategy_intents: dict[str, list[PositionIntent]],
        current_prices: dict[str, Decimal],
    ) -> AllocationResult:
        """
        Legacy equal-weight allocation (BACKWARD COMPATIBLE).

        Args:
            strategy_intents: Dict mapping strategy_name -> list of PositionIntent
            current_prices: Dict mapping symbol -> current price

        Returns:
            AllocationResult with equal-weight allocation
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
            f"Allocating ${self.config.max_positions_notional} across {num_strategies} strategies (LEGACY MODE)"
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
