"""Alpaca paper execution module with risk enforcement."""

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from src.app.config import Config
from src.app.models import OrderSide, OrderType
from src.broker import Broker
from src.market_data.fundamentals_cache import FundamentalsCache
from src.app.execution.tradability_filter import (
    ExecutionGateConfig,
    TradabilityGate,
)


@dataclass
class OrderInstruction:
    """Instruction to place an order."""

    symbol: str
    side: OrderSide
    quantity: int | float  # Support both whole and fractional shares
    limit_price: Decimal | None = None
    reason: str = ""
    is_risk_reducing: bool = False  # True if this order reduces exposure
    is_fractional: bool = False  # True if this is a fractional share order


@dataclass
class OrderSlice:
    """A slice of an order that fits within risk caps."""

    instruction: OrderInstruction
    slice_index: int
    total_slices: int


@dataclass
class ExecutionResult:
    """Result of execution attempt."""

    orders_placed: list[str]  # List of client_order_ids placed
    orders_skipped: list[tuple[str, str]]  # List of (symbol, reason) skipped
    dry_run: bool
    total_risk_used: Decimal  # Total notional of orders placed


class AlpacaExecutor:
    """
    Executor for placing orders on Alpaca paper trading.

    Enforces risk caps:
    - max_order_notional per order
    - max_positions_notional total exposure
    - max_daily_loss (basic check, full enforcement requires tracking)
    """

    def __init__(
        self,
        broker: Broker,
        config: Config,
        dry_run: bool = False,
        execution_gate_config: ExecutionGateConfig | None = None,
        fundamentals_cache: FundamentalsCache | None = None,
    ):
        """
        Initialize executor.

        Args:
            broker: Broker instance for order placement
            config: Trading configuration with risk parameters
            dry_run: If True, only print orders without placing
            execution_gate_config: Optional execution gate configuration (from mode profile)
            fundamentals_cache: Optional fundamentals cache (created if not provided)
        """
        self.broker = broker
        self.config = config
        self.dry_run = dry_run
        self.logger = logging.getLogger("ai-trader")

        # Initialize execution gate if config provided
        if execution_gate_config:
            if fundamentals_cache is None:
                fundamentals_cache = FundamentalsCache()
            self.execution_gate = TradabilityGate(execution_gate_config, fundamentals_cache)
            self.logger.info("Execution gate enabled with tradability filtering")
        else:
            self.execution_gate = None
            self.logger.info("Execution gate disabled (no constraints configured)")

    def reconcile_and_execute(
        self,
        target_positions: dict[str, int],
        current_prices: dict[str, Decimal],
    ) -> ExecutionResult:
        """
        Reconcile target positions with current positions and execute orders.

        Policy:
        - Symbols not in target_positions are treated as target=0 (flatten)
        - Orders that exceed max_order_notional are sliced into smaller orders
        - Risk-reducing sells (closing positions) always proceed (with slicing)
        - Risk-increasing orders subject to max_positions_notional cap

        Steps:
        1. Get current positions from broker
        2. Calculate required orders (delta between target and current)
        3. Slice orders that exceed max_order_notional
        4. Enforce risk caps (allowing risk-reducing sells)
        5. Place orders (or print if dry_run)

        Args:
            target_positions: Dict of symbol -> desired quantity
            current_prices: Dict of symbol -> current price

        Returns:
            ExecutionResult with placed orders and skipped orders
        """
        # Get current positions from broker
        current_positions = self.broker.get_positions()

        self.logger.info(f"Current positions: {current_positions}")
        self.logger.info(f"Target positions: {target_positions}")

        # Generate order instructions
        order_instructions = self._generate_order_instructions(
            target_positions, current_positions, current_prices
        )

        self.logger.info(f"Generated {len(order_instructions)} order instructions")

        # Print reconciliation summary
        print("\nReconciliation:")
        print(f"  {'Symbol':<8} {'Current':>8} {'Target':>8} {'Delta':>8} {'Action':<20}")
        print("  " + "-" * 60)
        all_symbols = set(target_positions.keys()) | set(current_positions.keys())
        for symbol in sorted(all_symbols):
            target_qty = target_positions.get(symbol, 0)
            current_qty = current_positions.get(symbol, (0, Decimal("0")))[0]
            delta = target_qty - current_qty
            if delta == 0:
                action = "No change"
            elif delta > 0:
                action = f"BUY {abs(delta)}"
            else:
                action = f"SELL {abs(delta)}"
            print(f"  {symbol:<8} {current_qty:>8} {target_qty:>8} {delta:>8} {action:<20}")
        print()

        # Execute orders with risk enforcement and slicing
        return self._execute_orders(order_instructions, current_prices, current_positions)

    def _generate_order_instructions(
        self,
        target_positions: dict[str, int],
        current_positions: dict[str, tuple[int, Decimal]],
        current_prices: dict[str, Decimal],
    ) -> list[OrderInstruction]:
        """
        Generate order instructions from position delta.

        Policy: Symbols not in target_positions are treated as target=0 (flatten).

        Args:
            target_positions: Dict of symbol -> desired quantity
            current_positions: Dict of symbol -> (current_qty, avg_price)
            current_prices: Dict of symbol -> current price

        Returns:
            List of OrderInstruction objects
        """
        instructions = []

        # Get all symbols we need to consider (current OR target)
        # This ensures we flatten positions not in target_positions
        all_symbols = set(target_positions.keys()) | set(current_positions.keys())

        for symbol in all_symbols:
            target_qty = target_positions.get(symbol, 0)  # Default to 0 if not in target
            current_qty = current_positions.get(symbol, (0, Decimal("0")))[0]
            delta = target_qty - current_qty

            if delta == 0:
                continue  # No change needed

            if symbol not in current_prices:
                self.logger.warning(f"{symbol}: No price available, skipping")
                continue

            price = current_prices[symbol]
            side = OrderSide.BUY if delta > 0 else OrderSide.SELL
            quantity = abs(delta)

            # Determine if this order reduces risk
            # SELL when we have a long position is risk-reducing
            # BUY when we have a short position would be risk-reducing (but we don't support shorts)
            is_risk_reducing = side == OrderSide.SELL and current_qty > 0

            # Use LIMIT order at current price (user requirement)
            # Add small offset: -0.5% for buys (more aggressive), +0.5% for sells
            offset = Decimal("-0.005") if side == OrderSide.BUY else Decimal("0.005")
            limit_price = price * (Decimal("1") + offset)
            limit_price = limit_price.quantize(Decimal("0.01"))  # Round to 2 decimals

            instruction = OrderInstruction(
                symbol=symbol,
                side=side,
                quantity=quantity,
                limit_price=limit_price,
                reason=f"Target={target_qty}, Current={current_qty}, Delta={delta}",
                is_risk_reducing=is_risk_reducing,
            )
            instructions.append(instruction)

        return instructions

    def _slice_order(self, instruction: OrderInstruction, price: Decimal) -> list[OrderSlice]:
        """
        Slice an order into cap-compliant chunks.

        Args:
            instruction: OrderInstruction to slice
            price: Current price for notional calculation

        Returns:
            List of OrderSlice objects, empty if order cannot fit within cap
        """
        order_notional = Decimal(str(instruction.quantity)) * price
        max_notional = self.config.max_order_notional

        # If order fits within cap, no slicing needed
        if order_notional <= max_notional:
            self.logger.debug(
                f"{instruction.symbol}: qty={instruction.quantity} notional=${float(order_notional):.2f} "
                f"<= cap=${float(max_notional):.2f} — no slicing"
            )
            return [OrderSlice(instruction=instruction, slice_index=1, total_slices=1)]

        # Calculate number of slices needed
        # Use limit price if available, else use current price
        effective_price = instruction.limit_price or price
        max_qty_per_slice = int(max_notional / effective_price)

        self.logger.info(
            f"{instruction.symbol}: SLICING — qty={instruction.quantity} "
            f"notional=${float(order_notional):.2f} "
            f"cap=${float(max_notional):.2f} "
            f"price=${float(effective_price):.2f} "
            f"max_qty_per_slice={max_qty_per_slice}"
        )

        if max_qty_per_slice == 0:
            # Price is too high for even 1 share to fit within cap
            # For risk-reducing orders (closing positions), allow 1 share minimum to enable exits
            # For risk-increasing orders (opening/adding), check if fractional is allowed
            if instruction.is_risk_reducing:
                max_qty_per_slice = 1
            elif self.config.allow_fractional and instruction.side == OrderSide.BUY:
                # Calculate fractional quantity that fits within cap
                fractional_qty = float(max_notional / effective_price)
                # Round to 3 decimals for safety (0.001 precision)
                fractional_qty = round(fractional_qty, 3)

                # Check minimum threshold (0.001)
                if fractional_qty >= 0.001:
                    # Create a single fractional order
                    fractional_instruction = OrderInstruction(
                        symbol=instruction.symbol,
                        side=instruction.side,
                        quantity=fractional_qty,
                        limit_price=instruction.limit_price,
                        reason=instruction.reason,
                        is_risk_reducing=instruction.is_risk_reducing,
                        is_fractional=True,
                    )
                    return [
                        OrderSlice(
                            instruction=fractional_instruction, slice_index=1, total_slices=1
                        )
                    ]
                else:
                    # Below minimum threshold, cannot proceed
                    return []
            else:
                # Fractional not allowed, cannot fit within cap, return empty to signal skip
                return []

        # Calculate total slices needed
        total_qty = instruction.quantity
        total_slices = (total_qty + max_qty_per_slice - 1) // max_qty_per_slice  # Ceiling division

        self.logger.info(
            f"{instruction.symbol}: {total_slices} slice(s) × {max_qty_per_slice} shares each "
            f"(${float(max_qty_per_slice * effective_price):.2f}/slice)"
        )

        # Create slices
        slices = []
        remaining_qty = total_qty

        for i in range(total_slices):
            slice_qty = min(max_qty_per_slice, remaining_qty)
            slice_instruction = OrderInstruction(
                symbol=instruction.symbol,
                side=instruction.side,
                quantity=slice_qty,
                limit_price=instruction.limit_price,
                reason=instruction.reason,
                is_risk_reducing=instruction.is_risk_reducing,
            )
            slices.append(
                OrderSlice(
                    instruction=slice_instruction,
                    slice_index=i + 1,
                    total_slices=total_slices,
                )
            )
            remaining_qty -= slice_qty

        return slices

    def _execute_orders(
        self,
        instructions: list[OrderInstruction],
        current_prices: dict[str, Decimal],
        current_positions: dict[str, tuple[int, Decimal]],
    ) -> ExecutionResult:
        """
        Execute order instructions with risk enforcement and slicing.

        Policy:
        - Orders exceeding max_order_notional are sliced into smaller orders
        - Risk-reducing sells always proceed (with slicing if needed)
        - Risk-increasing orders subject to max_positions_notional cap

        Args:
            instructions: List of OrderInstruction objects
            current_prices: Dict of symbol -> current price
            current_positions: Dict of symbol -> (current_qty, avg_price)

        Returns:
            ExecutionResult with placed/skipped orders
        """
        orders_placed = []
        orders_skipped = []
        total_risk_used = Decimal("0")

        # Calculate current exposure
        current_exposure = sum(
            abs(qty) * current_prices.get(symbol, Decimal("0"))
            for symbol, (qty, _) in current_positions.items()
            if symbol in current_prices
        )

        self.logger.info(f"Current portfolio exposure: ${current_exposure:.2f}")
        print(f"\nExecution (max_order_usd=${self.config.max_order_notional}):")

        for instruction in instructions:
            price = current_prices.get(instruction.symbol, Decimal("0"))
            if price == 0:
                self.logger.warning(f"{instruction.symbol}: No price available, skipping")
                orders_skipped.append((instruction.symbol, "No price available"))
                continue

            order_notional = instruction.quantity * (instruction.limit_price or price)

            # Slice order if it exceeds cap
            order_slices = self._slice_order(instruction, price)

            # Check if order cannot fit within cap (empty slices)
            if not order_slices:
                fractional_note = ""
                if not self.config.allow_fractional:
                    fractional_note = " (enable allow_fractional for fractional shares)"
                reason = (
                    f"Order notional ${order_notional:.2f} exceeds max_order_usd "
                    f"${self.config.max_order_notional} and cannot be sliced "
                    f"(single share notional: ${price * 1:.2f}){fractional_note}"
                )
                self.logger.warning(f"{instruction.symbol}: {reason}")
                orders_skipped.append((instruction.symbol, reason))
                print(f"  {instruction.symbol}: SKIPPED - {reason}")
                continue

            # Log if order was sliced
            if len(order_slices) > 1:
                print(
                    f"  {instruction.symbol}: Order ${order_notional:.2f} exceeds cap, "
                    f"slicing into {len(order_slices)} orders"
                )

            # Place each slice
            for order_slice in order_slices:
                slice_instruction = order_slice.instruction
                slice_notional = Decimal(str(slice_instruction.quantity)) * (
                    slice_instruction.limit_price or price
                )

                # For risk-increasing orders, check total exposure cap
                # Risk-reducing orders always proceed
                if not slice_instruction.is_risk_reducing:
                    new_exposure = current_exposure + slice_notional
                    if new_exposure > self.config.max_positions_notional:
                        reason = (
                            f"Total exposure ${new_exposure:.2f} would exceed "
                            f"max ${self.config.max_positions_notional}"
                        )
                        self.logger.warning(f"{slice_instruction.symbol}: {reason}")
                        orders_skipped.append((slice_instruction.symbol, reason))
                        continue

                # Check execution gate (hard tradability filter)
                # Risk-reducing sells always bypass the gate — we never block exits
                if self.execution_gate and not slice_instruction.is_risk_reducing:
                    tradability_result = self.execution_gate.check_tradability(
                        slice_instruction.symbol,
                        slice_instruction.limit_price or price,
                    )
                    if not tradability_result.allowed:
                        reason = (
                            f"BLOCKED by execution gate: {tradability_result.message} "
                            f"(reason: {tradability_result.reason.value if tradability_result.reason else 'unknown'})"
                        )
                        self.logger.warning(f"{slice_instruction.symbol}: {reason}")
                        orders_skipped.append((slice_instruction.symbol, reason))
                        print(f"  {slice_instruction.symbol}: BLOCKED - {tradability_result.message}")
                        continue

                # Place order (or dry-run)
                if self.dry_run:
                    self._print_dry_run_order(slice_instruction, order_slice)
                    orders_placed.append(
                        f"DRY-RUN-{slice_instruction.symbol}-{order_slice.slice_index}"
                    )
                else:
                    client_order_id = f"{slice_instruction.symbol}-{uuid.uuid4()}"
                    try:
                        order = self.broker.submit_order(
                            symbol=slice_instruction.symbol,
                            side=slice_instruction.side,
                            quantity=slice_instruction.quantity,
                            client_order_id=client_order_id,
                            order_type=OrderType.LIMIT,
                            limit_price=slice_instruction.limit_price,
                        )
                        self.logger.info(
                            f"Order placed: {slice_instruction.symbol} "
                            f"{slice_instruction.side.name} {slice_instruction.quantity} "
                            f"@ ${slice_instruction.limit_price} "
                            f"(slice {order_slice.slice_index}/{order_slice.total_slices}, ID: {order.id})"
                        )
                        orders_placed.append(client_order_id)
                    except Exception as e:
                        reason = f"Order submission failed: {e}"
                        self.logger.error(f"{slice_instruction.symbol}: {reason}")
                        orders_skipped.append((slice_instruction.symbol, reason))
                        continue

                # Update tracking
                total_risk_used += slice_notional
                if not slice_instruction.is_risk_reducing:
                    current_exposure += slice_notional
                else:
                    current_exposure -= slice_notional

        return ExecutionResult(
            orders_placed=orders_placed,
            orders_skipped=orders_skipped,
            dry_run=self.dry_run,
            total_risk_used=total_risk_used,
        )

    def _print_dry_run_order(
        self, instruction: OrderInstruction, order_slice: OrderSlice | None = None
    ):
        """
        Print order in dry-run format.

        Args:
            instruction: OrderInstruction to print
            order_slice: Optional OrderSlice info for sliced orders
        """
        slice_info = ""
        if order_slice and order_slice.total_slices > 1:
            slice_info = f" [slice {order_slice.slice_index}/{order_slice.total_slices}]"

        risk_tag = " (risk-reducing)" if instruction.is_risk_reducing else ""
        fractional_tag = " [fractional]" if instruction.is_fractional else ""

        # Format quantity with proper precision
        if instruction.is_fractional:
            qty_str = f"{instruction.quantity:.3f}"
        else:
            qty_str = f"{int(instruction.quantity)}"

        print(
            f"  [DRY-RUN] {instruction.symbol:<6} {instruction.side.name:<4} "
            f"{qty_str:>7} @ ${instruction.limit_price:>7.2f}  "
            f"({instruction.reason}){slice_info}{risk_tag}{fractional_tag}"
        )
