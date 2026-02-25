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

    def _compute_target_utilization(
        self,
        equity: Decimal,
        current_exposure: Decimal,
        target_exposure_pct: float,
        max_positions: int,
        current_positions: int,
        min_order_notional: float,
        per_position_max_pct: float,
    ) -> dict:
        """
        Compute per-order notional to hit target portfolio exposure.

        Uses remaining budget and available position slots to size orders that
        move utilization toward the target exposure percentage.

        Args:
            equity: Account equity
            current_exposure: Current portfolio exposure (sum of position values)
            target_exposure_pct: Target exposure as decimal (e.g., 0.60 for 60%)
            max_positions: Maximum number of concurrent positions
            current_positions: Number of open positions
            min_order_notional: Minimum notional per order
            per_position_max_pct: Maximum per-position as decimal (e.g., 0.15 for 15%)

        Returns:
            dict with keys: per_slot_notional, slots, remaining_budget, current_exposure_pct, reason
        """
        equity = Decimal(str(equity))
        current_exposure = Decimal(str(current_exposure))
        target_exposure = equity * Decimal(str(target_exposure_pct))
        remaining_budget = target_exposure - current_exposure
        slots_available = max_positions - current_positions

        current_exposure_pct = float(current_exposure / equity) if equity > 0 else 0.0

        if slots_available <= 0:
            return {
                "per_slot_notional": 0,
                "slots": 0,
                "remaining_budget": 0,
                "current_exposure_pct": current_exposure_pct,
                "reason": "max_positions_reached"
            }

        if remaining_budget <= 0:
            return {
                "per_slot_notional": 0,
                "slots": 0,
                "remaining_budget": float(remaining_budget),
                "current_exposure_pct": current_exposure_pct,
                "reason": "target_exposure_reached"
            }

        # Compute per-slot allocation
        per_slot = float(remaining_budget) / max(slots_available, 1)

        # Cap at per-position max
        per_position_max_notional = float(equity) * per_position_max_pct
        per_slot = min(per_slot, per_position_max_notional)

        if per_slot < min_order_notional:
            return {
                "per_slot_notional": 0,
                "slots": 0,
                "remaining_budget": float(remaining_budget),
                "current_exposure_pct": current_exposure_pct,
                "reason": "remaining_budget_too_small_for_min_order"
            }

        return {
            "per_slot_notional": per_slot,
            "slots": slots_available,
            "remaining_budget": float(remaining_budget),
            "current_exposure_pct": current_exposure_pct,
            "target_exposure_pct": target_exposure_pct,
            "reason": "ok"
        }

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
            # Check if broker has client attribute (AlpacaBroker) vs MockBroker
            if hasattr(self.broker, 'client'):
                account_state = self.broker.client.get_account()
                account_dict = {"equity": str(account_state.equity)}
                equity = allocation.get_total_equity(account_dict)
            else:
                # MockBroker in dry-run mode - use mock equity
                self.logger.info("MockBroker detected - using mock equity for allocation")
                equity = Decimal("100000.00")  # Mock $100k equity for dry-run
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
                    equity=float(equity),  # Convert Decimal to float for JSON serialization
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
            budget = allocation.compute_strategy_budget(float(equity), normalized_weight)
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
                        equity=float(equity),  # Convert Decimal to float for JSON serialization
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

        # TARGET UTILIZATION: Log current exposure and target metrics
        # (Full integration of target utilization sizing is TODO)
        try:
            if self.broker and hasattr(self.broker, 'get_positions'):
                positions = self.broker.get_positions()
                current_exposure = Decimal("0")
                for symbol, position in positions.items():
                    if isinstance(position, dict):
                        qty = position.get("qty", 0)
                        current_price_val = current_prices.get(symbol, Decimal("0"))
                    elif isinstance(position, tuple):
                        qty, _ = position
                        current_price_val = current_prices.get(symbol, Decimal("0"))
                    else:
                        qty = getattr(position, "qty", 0)
                        current_price_val = current_prices.get(symbol, Decimal("0"))

                    current_exposure += abs(int(qty)) * current_price_val

                current_positions_count = len([p for p in positions.values() if (isinstance(p, dict) and p.get("qty", 0) > 0) or (isinstance(p, tuple) and p[0] > 0) or (hasattr(p, "qty") and p.qty > 0)])

                # Log target utilization metrics (for instrumentation)
                target_exposure_pct = 0.60  # TODO: Load from mode config
                max_positions = 10  # TODO: Load from mode config
                util_info = self._compute_target_utilization(
                    equity=equity,
                    current_exposure=current_exposure,
                    target_exposure_pct=target_exposure_pct,
                    max_positions=max_positions,
                    current_positions=current_positions_count,
                    min_order_notional=500,  # TODO: Load from mode config
                    per_position_max_pct=0.15,  # TODO: Load from mode config
                )
                self.logger.info(
                    f"Target Utilization: {util_info['current_exposure_pct']:.1%} current, "
                    f"{util_info.get('target_exposure_pct', 0.6):.1%} target, "
                    f"${util_info['remaining_budget']:.2f} remaining, "
                    f"{util_info['slots']} slots available, "
                    f"${util_info['per_slot_notional']:.2f} per slot"
                )
                if util_info['reason'] != 'ok':
                    self.logger.warning(f"Target utilization issue: {util_info['reason']}")
        except Exception as e:
            self.logger.warning(f"Failed to compute target utilization metrics: {e}")

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

        # 5b. Apply target utilization scaling if enabled
        enable_target_utilization = self.config.enable_target_utilization if hasattr(self.config, 'enable_target_utilization') else False
        if enable_target_utilization:
            self.logger.info("Target utilization enabled - scaling netted notionals toward target exposure")

            # Load config params with defaults
            min_order_notional = getattr(self.config, 'min_order_notional', 500)
            allow_position_adds = getattr(self.config, 'allow_position_adds', False)
            target_exposure_pct = getattr(self.config, 'max_portfolio_exposure_pct', 0.60)
            max_positions = getattr(self.config, 'max_positions', 10)
            per_position_max_pct = getattr(self.config, 'max_per_position_pct', 0.15)

            # Compute current exposure (reuse from target utilization logging above)
            current_exposure = Decimal("0")
            current_positions_count = 0
            try:
                if self.broker and hasattr(self.broker, 'get_positions'):
                    positions = self.broker.get_positions()
                    for symbol, position in positions.items():
                        if isinstance(position, dict):
                            qty = position.get("qty", 0)
                            current_price_val = current_prices.get(symbol, Decimal("0"))
                        elif isinstance(position, tuple):
                            qty, _ = position
                            current_price_val = current_prices.get(symbol, Decimal("0"))
                        else:
                            qty = getattr(position, "qty", 0)
                            current_price_val = current_prices.get(symbol, Decimal("0"))

                        current_exposure += abs(int(qty)) * current_price_val

                    current_positions_count = len([p for p in positions.values() if (isinstance(p, dict) and p.get("qty", 0) > 0) or (isinstance(p, tuple) and p[0] > 0) or (hasattr(p, "qty") and p.qty > 0)])
            except Exception as e:
                self.logger.warning(f"Failed to compute current exposure for scaling: {e}")
                current_exposure = Decimal("0")
                current_positions_count = 0

            # If allow_position_adds is False, filter out symbols with existing positions
            if not allow_position_adds:
                existing_symbols = set()
                try:
                    if self.broker and hasattr(self.broker, 'get_positions'):
                        positions = self.broker.get_positions()
                        for symbol, position in positions.items():
                            if isinstance(position, dict):
                                qty = position.get("qty", 0)
                            elif isinstance(position, tuple):
                                qty, _ = position
                            else:
                                qty = getattr(position, "qty", 0)
                            if qty > 0:
                                existing_symbols.add(symbol)
                except Exception as e:
                    self.logger.warning(f"Failed to check existing positions: {e}")

                if existing_symbols:
                    filtered_netted = {s: data for s, data in netted_results.items() if s not in existing_symbols}
                    filtered_count = len(netted_results) - len(filtered_netted)
                    if filtered_count > 0:
                        self.logger.info(f"Filtered out {filtered_count} symbols with existing positions (allow_position_adds=False)")
                        netted_results = filtered_netted

            # Scale notionals toward target utilization
            netted_results = allocation.scale_notionals_for_target_utilization(
                netted_results=netted_results,
                equity=float(equity),
                current_exposure=float(current_exposure),
                target_exposure_pct=target_exposure_pct,
                max_positions=max_positions,
                current_positions=current_positions_count,
                min_order_notional=min_order_notional,
                per_position_max_pct=per_position_max_pct,
            )
            self.logger.info(f"After target utilization scaling: {len(netted_results)} symbols remain")

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

        Can be bypassed via UI toggle (data/ui_runtime_overrides.json).

        Args:
            targets: Dict of symbol -> target quantity
            prices: Dict of symbol -> current price
            warnings: List to append warnings to

        Returns:
            Capped target positions
        """
        # Check if capital limit bypass is enabled
        bypass_capital_limit = False
        try:
            import json
            from pathlib import Path

            ui_overrides_path = Path("data/ui_runtime_overrides.json")
            if ui_overrides_path.exists():
                with open(ui_overrides_path, "r") as f:
                    overrides = json.load(f)
                    bypass_capital_limit = overrides.get("allocator", {}).get("bypass_capital_limit", False)
        except Exception as e:
            self.logger.warning(f"Failed to load bypass setting, using default (False): {e}")

        if bypass_capital_limit:
            self.logger.warning("⚠️  CAPITAL LIMIT BYPASSED - max_positions_notional NOT enforced!")
            warnings.append("Capital limit bypassed - no max_positions_notional cap applied")
            # Return all targets without capping
            return {symbol: qty for symbol, qty in targets.items() if qty != 0}

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
