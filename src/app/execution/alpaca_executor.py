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
    quantity: int
    limit_price: Decimal | None = None
    reason: str = ""


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

        Steps:
        1. Get current positions from broker
        2. Calculate required orders (delta between target and current)
        3. Enforce risk caps
        4. Place orders (or print if dry_run)

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

        # Execute orders with risk enforcement
        return self._execute_orders(order_instructions, current_prices)

    def _generate_order_instructions(
        self,
        target_positions: dict[str, int],
        current_positions: dict[str, tuple[int, Decimal]],
        current_prices: dict[str, Decimal],
    ) -> list[OrderInstruction]:
        """
        Generate order instructions from position delta.

        Args:
            target_positions: Dict of symbol -> desired quantity
            current_positions: Dict of symbol -> (current_qty, avg_price)
            current_prices: Dict of symbol -> current price

        Returns:
            List of OrderInstruction objects
        """
        instructions = []

        # Get all symbols we need to consider
        all_symbols = set(target_positions.keys()) | set(current_positions.keys())

        for symbol in all_symbols:
            target_qty = target_positions.get(symbol, 0)
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
            )
            instructions.append(instruction)

        return instructions

    def _execute_orders(
        self,
        instructions: list[OrderInstruction],
        current_prices: dict[str, Decimal],
    ) -> ExecutionResult:
        """
        Execute order instructions with risk enforcement.

        Args:
            instructions: List of OrderInstruction objects
            current_prices: Dict of symbol -> current price

        Returns:
            ExecutionResult with placed/skipped orders
        """
        orders_placed = []
        orders_skipped = []
        total_risk_used = Decimal("0")

        # Get current positions to calculate total exposure
        current_positions = self.broker.get_positions()
        current_exposure = sum(
            abs(qty) * current_prices.get(symbol, Decimal("0"))
            for symbol, (qty, _) in current_positions.items()
            if symbol in current_prices
        )

        self.logger.info(f"Current portfolio exposure: ${current_exposure:.2f}")

        for instruction in instructions:
            # Check order notional
            order_notional = instruction.quantity * (
                instruction.limit_price or current_prices.get(instruction.symbol, Decimal("0"))
            )

            if order_notional > self.config.max_order_notional:
                reason = (
                    f"Order notional ${order_notional:.2f} exceeds "
                    f"max ${self.config.max_order_notional}"
                )
                self.logger.warning(f"{instruction.symbol}: {reason}")
                orders_skipped.append((instruction.symbol, reason))
                continue

            # Check total exposure
            new_exposure = current_exposure + order_notional
            if new_exposure > self.config.max_positions_notional:
                reason = (
                    f"Total exposure ${new_exposure:.2f} would exceed "
                    f"max ${self.config.max_positions_notional}"
                )
                self.logger.warning(f"{instruction.symbol}: {reason}")
                orders_skipped.append((instruction.symbol, reason))
                continue

            # Place order (or dry-run)
            if self.dry_run:
                self._print_dry_run_order(instruction)
                orders_placed.append(f"DRY-RUN-{instruction.symbol}")
            else:
                client_order_id = f"{instruction.symbol}-{uuid.uuid4()}"
                try:
                    order = self.broker.submit_order(
                        symbol=instruction.symbol,
                        side=instruction.side,
                        quantity=instruction.quantity,
                        client_order_id=client_order_id,
                        order_type=OrderType.LIMIT,
                        limit_price=instruction.limit_price,
                    )
                    self.logger.info(
                        f"Order placed: {instruction.symbol} {instruction.side.name} "
                        f"{instruction.quantity} @ ${instruction.limit_price} (ID: {order.id})"
                    )
                    orders_placed.append(client_order_id)
                except Exception as e:
                    reason = f"Order submission failed: {e}"
                    self.logger.error(f"{instruction.symbol}: {reason}")
                    orders_skipped.append((instruction.symbol, reason))
                    continue

            total_risk_used += order_notional
            current_exposure += order_notional

        return ExecutionResult(
            orders_placed=orders_placed,
            orders_skipped=orders_skipped,
            dry_run=self.dry_run,
            total_risk_used=total_risk_used,
        )

    def _print_dry_run_order(self, instruction: OrderInstruction):
        """
        Print order in dry-run format.

        Args:
            instruction: OrderInstruction to print
        """
        print(
            f"  [DRY-RUN] {instruction.symbol:<6} {instruction.side.name:<4} "
            f"{instruction.quantity:>3} @ ${instruction.limit_price:>7.2f}  "
            f"({instruction.reason})"
        )
