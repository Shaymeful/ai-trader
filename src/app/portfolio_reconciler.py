"""Portfolio reconciler for capital cap enforcement and universe alignment.

This module ensures the portfolio stays aligned with:
1. Capital cap (max_gross_exposure_usd)
2. Enabled sectors (universe registry)
3. Ticker exclusions (bad news evaluator)

It generates sell orders to bring the portfolio back into compliance.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.app.config import Config
from src.app.sell_reasons import SellReason, format_reason_for_logging

logger = logging.getLogger(__name__)


@dataclass
class SellIntent:
    """Intent to sell a position with reason and context."""

    symbol: str
    quantity: int  # Shares to sell (positive number)
    reason: SellReason
    priority: int  # Lower = higher priority
    context: dict[str, Any]  # Additional context for logging


@dataclass
class ReconciliationResult:
    """Result of portfolio reconciliation."""

    sell_intents: list[SellIntent]  # Ordered by priority
    current_exposure: Decimal
    target_exposure: Decimal
    cap: Decimal
    violations: list[str]  # Human-readable violations found


class PortfolioReconciler:
    """
    Reconciles portfolio to enforce capital caps and universe alignment.

    Call flow:
    1. reconcile() - main entry point
    2. _check_capital_cap() - enforce max_gross_exposure
    3. _check_sector_alignment() - enforce disabled sectors
    4. _check_ticker_exclusions() - enforce bad news exclusions
    5. Returns ordered sell intents (by priority)
    """

    def __init__(
        self,
        config: Config,
        universe_registry=None,
        excluded_tickers: dict[str, dict] | None = None,
    ):
        """
        Initialize reconciler.

        Args:
            config: Trading configuration
            universe_registry: Optional UniverseRegistry for sector state
            excluded_tickers: Optional dict of {symbol: {reason, confidence, ttl}} for bad news exclusions
        """
        self.config = config
        self.universe_registry = universe_registry
        self.excluded_tickers = excluded_tickers or {}

    def reconcile(
        self,
        positions: dict[str, tuple[int, Decimal]],
        current_prices: dict[str, Decimal],
    ) -> ReconciliationResult:
        """
        Reconcile portfolio to enforce all constraints.

        Args:
            positions: Dict of {symbol: (quantity, avg_entry_price)}
            current_prices: Dict of {symbol: current_price}

        Returns:
            ReconciliationResult with sell intents ordered by priority
        """
        sell_intents: list[SellIntent] = []
        violations: list[str] = []

        # Calculate current exposure
        current_exposure = self._calculate_gross_exposure(positions)
        cap = self.config.max_positions_notional

        # DIAGNOSTIC LOGGING
        logger.info("="*80)
        logger.info("PORTFOLIO RECONCILIATION START")
        logger.info("="*80)
        logger.info(f"Config source: max_positions_notional from config object")
        logger.info(f"Capital cap: ${cap:,.2f}")
        logger.info(f"Current exposure: ${current_exposure:,.2f}")
        logger.info(f"Positions count: {len(positions)}")
        logger.info(f"Utilization: {(current_exposure / cap * 100) if cap > 0 else 0:.1f}%")

        if cap is None or cap <= 0:
            error_msg = f"CRITICAL: Capital cap is invalid (cap={cap}). Cannot reconcile."
            logger.error(error_msg)
            raise ValueError(error_msg)

        for symbol, (qty, avg_price) in positions.items():
            notional = Decimal(qty) * avg_price
            logger.info(f"  {symbol}: qty={qty}, avg_price=${avg_price:.2f}, notional=${notional:,.2f}")

        logger.info(f"Reconciling portfolio: exposure=${current_exposure:.2f}, cap=${cap:.2f}")

        # Check 1: Ticker exclusions (highest priority after risk)
        exclusion_intents, exclusion_violations = self._check_ticker_exclusions(
            positions, current_prices
        )
        sell_intents.extend(exclusion_intents)
        violations.extend(exclusion_violations)

        # Check 2: Sector alignment - REMOVED
        # Now handled manually via "Exit Disabled Positions" button
        # which uses Exit Advisor AI to find optimal exit timing

        # Check 3: Capital cap (after removing exclusions)
        # Recalculate exposure after planned sells
        remaining_exposure = current_exposure
        for intent in sell_intents:
            qty = intent.quantity
            price = current_prices.get(intent.symbol, Decimal("0"))
            remaining_exposure -= Decimal(qty) * price

        cap_intents, cap_violations = self._check_capital_cap(
            positions, current_prices, sell_intents, remaining_exposure
        )
        sell_intents.extend(cap_intents)
        violations.extend(cap_violations)

        # Sort by priority (lower number = higher priority)
        sell_intents.sort(key=lambda x: x.priority)

        # Log violations
        if violations:
            logger.warning(f"Portfolio violations detected: {len(violations)} issues")
            for violation in violations:
                logger.warning(f"  - {violation}")

        # Log sell intents
        if sell_intents:
            logger.info(f"Generated {len(sell_intents)} sell intents:")
            for intent in sell_intents:
                log_msg = format_reason_for_logging(intent.reason, intent.context)
                logger.info(f"  {log_msg}")

        # Calculate target exposure after all sells
        target_exposure = remaining_exposure
        for intent in cap_intents:
            qty = intent.quantity
            price = current_prices.get(intent.symbol, Decimal("0"))
            target_exposure -= Decimal(qty) * price

        # DIAGNOSTIC LOGGING - Results
        logger.info("="*80)
        logger.info("RECONCILIATION RESULTS")
        logger.info("="*80)
        logger.info(f"Sell intents generated: {len(sell_intents)}")
        logger.info(f"Violations found: {len(violations)}")
        logger.info(f"Target exposure after sells: ${target_exposure:,.2f}")
        logger.info(f"Exposure reduction: ${current_exposure - target_exposure:,.2f}")

        if sell_intents:
            logger.info("SELL INTENTS (ordered by priority):")
            for i, intent in enumerate(sell_intents, 1):
                logger.info(f"  {i}. {intent.symbol}: qty={intent.quantity}, reason={intent.reason.value}, priority={intent.priority}")
        else:
            logger.info("NO SELL INTENTS - Portfolio compliant")

        logger.info("="*80)

        return ReconciliationResult(
            sell_intents=sell_intents,
            current_exposure=current_exposure,
            target_exposure=target_exposure,
            cap=cap,
            violations=violations,
        )

    def _calculate_gross_exposure(self, positions: dict[str, tuple[int, Decimal]]) -> Decimal:
        """
        Calculate gross exposure = sum(qty * avg_price) for all positions.

        Args:
            positions: Dict of {symbol: (quantity, avg_entry_price)}

        Returns:
            Total gross exposure
        """
        exposure = Decimal("0")
        for symbol, (qty, avg_price) in positions.items():
            exposure += Decimal(qty) * avg_price
        return exposure

    def _check_ticker_exclusions(
        self,
        positions: dict[str, tuple[int, Decimal]],
        current_prices: dict[str, Decimal],
    ) -> tuple[list[SellIntent], list[str]]:
        """
        Check for positions in excluded tickers (bad news).

        Args:
            positions: Current positions
            current_prices: Current prices

        Returns:
            Tuple of (sell_intents, violations)
        """
        intents: list[SellIntent] = []
        violations: list[str] = []

        for symbol, (qty, avg_price) in positions.items():
            if symbol in self.excluded_tickers:
                exclusion_info = self.excluded_tickers[symbol]
                reason_text = exclusion_info.get("reason", "unknown")
                confidence = exclusion_info.get("confidence", 0.0)

                # Create sell intent for full position
                price = current_prices.get(symbol, avg_price)
                notional = float(Decimal(qty) * price)

                intent = SellIntent(
                    symbol=symbol,
                    quantity=qty,
                    reason=SellReason.TICKER_EXCLUDED_NEWS,
                    priority=20,  # High priority (see get_reason_priority)
                    context={
                        "symbol": symbol,
                        "quantity": qty,
                        "notional": notional,
                        "confidence": confidence,
                        "rationale": reason_text,
                    },
                )

                intents.append(intent)
                violations.append(
                    f"Position in excluded ticker {symbol}: {qty} shares, reason: {reason_text}"
                )

        return intents, violations

    def _check_sector_alignment(
        self,
        positions: dict[str, tuple[int, Decimal]],
        current_prices: dict[str, Decimal],
    ) -> tuple[list[SellIntent], list[str]]:
        """
        Check for positions in disabled sectors.

        Args:
            positions: Current positions
            current_prices: Current prices

        Returns:
            Tuple of (sell_intents, violations)
        """
        intents: list[SellIntent] = []
        violations: list[str] = []

        if self.universe_registry is None:
            # No universe registry - skip sector checks
            return intents, violations

        # Build reverse map: symbol -> sector_name
        symbol_to_sector: dict[str, str] = {}
        for sector_name, sector_config in self.universe_registry.sectors.items():
            for symbol in sector_config.symbols:
                symbol_to_sector[symbol] = sector_name

        # Check each position
        for symbol, (qty, avg_price) in positions.items():
            sector_name = symbol_to_sector.get(symbol)

            if sector_name is None:
                # Symbol not in any known sector - could be legacy position
                logger.debug(f"Position {symbol} not in any sector - keeping")
                continue

            sector_config = self.universe_registry.sectors[sector_name]

            if not sector_config.enabled:
                # Position in disabled sector - schedule for liquidation
                price = current_prices.get(symbol, avg_price)
                notional = float(Decimal(qty) * price)

                intent = SellIntent(
                    symbol=symbol,
                    quantity=qty,
                    reason=SellReason.SECTOR_DISABLED,
                    priority=21,  # High priority (see get_reason_priority)
                    context={
                        "symbol": symbol,
                        "quantity": qty,
                        "notional": notional,
                        "sector": sector_name,
                    },
                )

                intents.append(intent)
                violations.append(
                    f"Position {symbol} in disabled sector '{sector_name}': {qty} shares"
                )

        return intents, violations

    def _check_capital_cap(
        self,
        positions: dict[str, tuple[int, Decimal]],
        current_prices: dict[str, Decimal],
        existing_intents: list[SellIntent],
        current_exposure: Decimal,
    ) -> tuple[list[SellIntent], list[str]]:
        """
        Check if capital cap is exceeded and generate sells to bring under cap.

        Uses deterministic liquidation policy:
        1. Lowest absolute return (worst performers first)
        2. Oldest positions (if returns are equal)
        3. Deterministic tie-breaker (alphabetical by symbol)

        Args:
            positions: Current positions
            current_prices: Current prices
            existing_intents: Already-scheduled sells (to avoid double-counting)
            current_exposure: Current gross exposure

        Returns:
            Tuple of (sell_intents, violations)
        """
        intents: list[SellIntent] = []
        violations: list[str] = []

        cap = self.config.max_positions_notional

        # Check if over cap
        if current_exposure <= cap:
            logger.info(
                f"Portfolio within cap: ${current_exposure:.2f} <= ${cap:.2f} (no action needed)"
            )
            return intents, violations

        # Over cap - need to liquidate
        overage = current_exposure - cap
        logger.warning(
            f"Portfolio OVER CAP: ${current_exposure:.2f} > ${cap:.2f} (overage: ${overage:.2f})"
        )

        violations.append(
            f"Capital cap exceeded: ${current_exposure:.2f} > ${cap:.2f} (overage: ${overage:.2f})"
        )

        # Build set of symbols already scheduled for sale
        already_selling = {intent.symbol for intent in existing_intents}

        # Score each position for liquidation priority
        # Lower score = liquidate first
        position_scores: list[tuple[str, float, Decimal]] = []

        for symbol, (qty, avg_price) in positions.items():
            if symbol in already_selling:
                # Already selling this position - skip
                continue

            price = current_prices.get(symbol, avg_price)

            # Calculate absolute return
            abs_return = float((price - avg_price) * Decimal(qty))

            # Score = absolute_return (worst performers have lowest/most negative)
            # Tie-breaker: alphabetical
            score = abs_return

            notional = Decimal(qty) * price
            position_scores.append((symbol, score, notional))

        # Sort by score (ascending = worst performers first)
        position_scores.sort(key=lambda x: (x[1], x[0]))  # score, then symbol

        # Liquidate positions until we're under cap
        remaining_overage = overage
        for symbol, score, notional in position_scores:
            if remaining_overage <= Decimal("0"):
                break  # Under cap now

            qty, avg_price = positions[symbol]
            price = current_prices.get(symbol, avg_price)

            # Determine sell quantity
            # Strategy: Sell full position if it helps, otherwise partial
            position_notional = Decimal(qty) * price

            if position_notional <= remaining_overage:
                # Sell entire position
                sell_qty = qty
                sell_notional = position_notional
            else:
                # Partial sell - only sell enough to get under cap
                # Calculate shares needed
                shares_needed = int(remaining_overage / price)
                sell_qty = max(1, shares_needed)  # At least 1 share
                sell_notional = Decimal(sell_qty) * price

            intent = SellIntent(
                symbol=symbol,
                quantity=sell_qty,
                reason=SellReason.CAP_EXCEEDED,
                priority=10,  # Medium priority (see get_reason_priority)
                context={
                    "symbol": symbol,
                    "quantity": sell_qty,
                    "notional": float(sell_notional),
                    "current_exposure": float(current_exposure),
                    "cap": float(cap),
                    "abs_return": score,
                },
            )

            intents.append(intent)
            remaining_overage -= sell_notional
            current_exposure -= sell_notional

            logger.info(
                f"Cap overage sell: {symbol} qty={sell_qty} notional=${sell_notional:.2f} "
                f"abs_return=${score:.2f} remaining_overage=${remaining_overage:.2f}"
            )

        return intents, violations
