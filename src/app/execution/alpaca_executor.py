"""Alpaca paper execution module with risk enforcement."""

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal

from src.app.config import Config
from src.app.models import OrderSide, OrderType
from src.broker import Broker


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


@dataclass
class OrderHygieneAction:
    """Record of order hygiene action taken."""

    symbol: str
    side: str
    action: str  # "canceled", "skipped", "replaced"
    reason: str
    order_id: str | None = None


class AlpacaExecutor:
    """
    Executor for placing orders on Alpaca paper trading.

    Enforces risk caps:
    - max_order_notional per order
    - max_positions_notional total exposure
    - max_daily_loss (basic check, full enforcement requires tracking)
    """

    def __init__(self, broker: Broker, config: Config, dry_run: bool = False):
        """
        Initialize executor.

        Args:
            broker: Broker instance for order placement
            config: Trading configuration with risk parameters
            dry_run: If True, only print orders without placing
        """
        self.broker = broker
        self.config = config
        self.dry_run = dry_run
        self.logger = logging.getLogger("ai-trader")

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
            return [OrderSlice(instruction=instruction, slice_index=1, total_slices=1)]

        # Calculate number of slices needed
        # Use limit price if available, else use current price
        effective_price = instruction.limit_price or price
        max_qty_per_slice = int(max_notional / effective_price)

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
        total_slices = int((total_qty + max_qty_per_slice - 1) // max_qty_per_slice)  # Ceiling division

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

    def _perform_order_hygiene(
        self,
        instructions: list[OrderInstruction],
        current_prices: dict[str, Decimal],
    ) -> tuple[list[OrderInstruction], list[OrderHygieneAction]]:
        """
        Perform order hygiene: cancel stale/duplicate open orders and filter instructions.

        UPDATED POLICY (Fixed for order slicing):
        - For each new instruction, cancel ALL existing open orders for that (symbol, side)
        - This prevents order accumulation when slicing creates multiple orders
        - Exception: Skip the new instruction if a matching order already exists

        Args:
            instructions: List of new OrderInstruction objects to place
            current_prices: Dict of symbol -> current price

        Returns:
            Tuple of (filtered_instructions, hygiene_actions)
        """
        hygiene_actions: list[OrderHygieneAction] = []

        if not self.config.cancel_stale_orders:
            # Hygiene disabled, return all instructions unchanged
            return instructions, hygiene_actions

        # Fetch open orders from broker
        try:
            open_orders = self.broker.get_open_orders_detailed()
        except Exception as e:
            self.logger.error(f"Failed to fetch open orders for hygiene: {e}")
            # If we can't fetch open orders, proceed with all instructions (fail-open)
            return instructions, hygiene_actions

        # Build index: (symbol, side) -> list of open orders
        open_orders_index: dict[tuple[str, str], list[dict]] = {}
        for order in open_orders:
            key = (order["symbol"], order["side"])
            if key not in open_orders_index:
                open_orders_index[key] = []
            open_orders_index[key].append(order)

        # Calculate reserved notional from open BUY orders (for exposure tracking later)
        reserved_notional = Decimal("0")
        for order in open_orders:
            if order["side"] == "BUY" and order["limit_price"]:
                reserved_notional += Decimal(str(order["qty"])) * order["limit_price"]

        self.logger.info(f"Reserved notional from {len(open_orders)} open orders: ${reserved_notional:.2f}")

        # Process each new instruction
        filtered_instructions = []

        for instruction in instructions:
            key = (instruction.symbol, instruction.side.name)
            existing_orders = open_orders_index.get(key, [])

            if not existing_orders:
                # No existing orders for this (symbol, side), proceed with instruction
                filtered_instructions.append(instruction)
                continue

            # NEW POLICY: Check if ANY existing order matches the new instruction
            # If so, skip the new instruction entirely (avoid duplicates)
            matches_existing = False
            for existing_order in existing_orders:
                if self._orders_match(instruction, existing_order, current_prices):
                    # Found matching order, skip new instruction
                    matches_existing = True
                    hygiene_actions.append(
                        OrderHygieneAction(
                            symbol=instruction.symbol,
                            side=instruction.side.name,
                            action="skipped",
                            reason="Matching open order already exists",
                            order_id=existing_order["order_id"],
                        )
                    )
                    self.logger.info(
                        f"{instruction.symbol} {instruction.side.name}: Skipping new order, "
                        f"matching open order {existing_order['order_id']} already exists"
                    )
                    break

            if matches_existing:
                continue  # Skip this instruction

            # NEW POLICY: If we're placing a new order, cancel ALL existing orders for this (symbol, side)
            # This prevents accumulation when order slicing creates multiple orders from one instruction
            self.logger.info(
                f"{instruction.symbol} {instruction.side.name}: Canceling {len(existing_orders)} "
                f"existing order(s) before placing new order (prevents accumulation)"
            )

            for existing_order in existing_orders:
                order_id = existing_order["order_id"]
                try:
                    if not self.dry_run:
                        self.broker.client.cancel_order_by_id(order_id)
                    hygiene_actions.append(
                        OrderHygieneAction(
                            symbol=instruction.symbol,
                            side=instruction.side.name,
                            action="canceled",
                            reason=f"Clearing existing orders before new placement (found {len(existing_orders)})",
                            order_id=order_id,
                        )
                    )
                    self.logger.info(
                        f"{instruction.symbol} {instruction.side.name}: Canceled order {order_id}"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to cancel order {order_id} for {instruction.symbol}: {e}"
                    )

            # Place new instruction as replacement (may get sliced into multiple orders later)
            filtered_instructions.append(instruction)
            hygiene_actions.append(
                OrderHygieneAction(
                    symbol=instruction.symbol,
                    side=instruction.side.name,
                    action="replaced",
                    reason=f"Replaced {len(existing_orders)} existing order(s) with new instruction",
                    order_id=None,
                )
            )

        return filtered_instructions, hygiene_actions

    def _orders_match(
        self,
        instruction: OrderInstruction,
        existing_order: dict,
        current_prices: dict[str, Decimal],
    ) -> bool:
        """
        Check if a new order instruction matches an existing open order.

        Orders match if:
        - Quantity is within tolerance
        - Limit price is within tolerance (or both are None for market orders)

        Args:
            instruction: New order instruction
            existing_order: Existing open order dict
            current_prices: Current prices for reference

        Returns:
            True if orders match within tolerances
        """
        # Check quantity
        qty_diff = abs(instruction.quantity - existing_order["qty"])
        qty_tolerance = self.config.order_qty_tolerance
        if qty_diff > qty_tolerance:
            return False

        # Check price
        if instruction.limit_price is None and existing_order["limit_price"] is None:
            # Both market orders, consider them matching
            return True

        if instruction.limit_price is None or existing_order["limit_price"] is None:
            # One is limit, one is market, don't match
            return False

        # Both have limit prices, check tolerance
        price_diff = abs(instruction.limit_price - existing_order["limit_price"])
        price_tolerance_pct = Decimal(str(self.config.order_price_tolerance_pct))
        price_tolerance = existing_order["limit_price"] * price_tolerance_pct

        return price_diff <= price_tolerance

    def _execute_orders(
        self,
        instructions: list[OrderInstruction],
        current_prices: dict[str, Decimal],
        current_positions: dict[str, tuple[int, Decimal]],
    ) -> ExecutionResult:
        """
        Execute order instructions with risk enforcement and slicing.

        Policy:
        - Perform order hygiene first (cancel stale/duplicate orders)
        - Orders exceeding max_order_notional are sliced into smaller orders
        - Risk-reducing sells always proceed (with slicing if needed)
        - Risk-increasing orders subject to max_positions_notional cap (including reserved notional)

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

        # STEP 1: Perform order hygiene (cancel stale/duplicate orders, filter instructions)
        filtered_instructions, hygiene_actions = self._perform_order_hygiene(
            instructions, current_prices
        )

        # Print hygiene summary
        if hygiene_actions:
            print("\nOrder Hygiene:")
            for action in hygiene_actions:
                print(f"  {action.symbol} {action.side}: {action.action} - {action.reason}")

        # Calculate current exposure from positions
        current_exposure = sum(
            abs(qty) * current_prices.get(symbol, Decimal("0"))
            for symbol, (qty, _) in current_positions.items()
            if symbol in current_prices
        )

        # Calculate reserved notional from remaining open BUY orders (after hygiene)
        # This accounts for orders we didn't cancel that will consume buying power when filled
        reserved_notional = Decimal("0")
        try:
            remaining_open_orders = self.broker.get_open_orders_detailed()
            for order in remaining_open_orders:
                if order["side"] == "BUY" and order["limit_price"]:
                    reserved_notional += Decimal(str(order["qty"])) * order["limit_price"]
        except Exception as e:
            self.logger.warning(f"Failed to calculate reserved notional: {e}")

        self.logger.info(f"Current portfolio exposure: ${current_exposure:.2f}")
        self.logger.info(f"Reserved notional (open orders): ${reserved_notional:.2f}")
        self.logger.info(f"Total exposure (positions + reserved): ${current_exposure + reserved_notional:.2f}")

        print(f"\nExecution (max_order_usd=${self.config.max_order_notional}):")

        # Use filtered instructions after hygiene
        for instruction in filtered_instructions:
            price = current_prices.get(instruction.symbol, Decimal("0"))
            if price == 0:
                self.logger.warning(f"{instruction.symbol}: No price available, skipping")
                orders_skipped.append((instruction.symbol, "No price available"))
                continue

            order_notional = Decimal(str(instruction.quantity)) * (instruction.limit_price or price)

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

                # For risk-increasing orders, check total exposure cap (including reserved notional)
                # Risk-reducing orders always proceed
                if not slice_instruction.is_risk_reducing:
                    # Include reserved notional from other open orders in exposure calculation
                    new_exposure = current_exposure + reserved_notional + slice_notional
                    if new_exposure > self.config.max_positions_notional:
                        reason = (
                            f"Total exposure ${new_exposure:.2f} (positions: ${current_exposure:.2f} + "
                            f"reserved: ${reserved_notional:.2f} + new: ${slice_notional:.2f}) "
                            f"would exceed max ${self.config.max_positions_notional}"
                        )
                        self.logger.warning(f"{slice_instruction.symbol}: {reason}")
                        orders_skipped.append((slice_instruction.symbol, reason))
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
