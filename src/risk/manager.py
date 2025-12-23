"""Risk management and position validation."""

from decimal import Decimal

from src.app.config import Config
from src.app.models import OrderSide, Position, Signal


class RiskCheckResult:
    """Result of a risk check."""

    def __init__(self, passed: bool, reason: str = ""):
        self.passed = passed
        self.reason = reason

    def __bool__(self):
        return self.passed


class RiskManager:
    """Manages risk checks for trading decisions."""

    def __init__(self, config: Config, daily_realized_pnl: Decimal = Decimal("0")):
        """
        Initialize risk manager.

        Args:
            config: Trading configuration
            daily_realized_pnl: Current day's realized PnL (from state)
        """
        self.config = config
        self.daily_pnl = daily_realized_pnl
        self.positions: dict[str, Position] = {}

    def check_signal(self, signal: Signal) -> RiskCheckResult:
        """
        Check if a signal passes all risk constraints.

        Args:
            signal: Trading signal to validate

        Returns:
            RiskCheckResult with pass/fail and reason
        """
        # Check symbol allowlist
        if signal.symbol not in self.config.allowed_symbols:
            return RiskCheckResult(False, f"Symbol {signal.symbol} not in allowlist")

        # Check max positions
        if signal.side == OrderSide.BUY and len(self.positions) >= self.config.max_positions:
            return RiskCheckResult(False, f"Max positions ({self.config.max_positions}) reached")

        # Check daily loss limit
        if self.daily_pnl <= -self.config.max_daily_loss:
            return RiskCheckResult(
                False, f"Daily loss limit ({self.config.max_daily_loss}) exceeded"
            )

        return RiskCheckResult(True, "All checks passed")

    def check_order_quantity(self, quantity: int) -> RiskCheckResult:
        """
        Check if order quantity is within limits.

        Args:
            quantity: Order quantity to check

        Returns:
            RiskCheckResult with pass/fail and reason
        """
        if quantity > self.config.max_order_quantity:
            return RiskCheckResult(
                False, f"Order quantity {quantity} exceeds max {self.config.max_order_quantity}"
            )

        if quantity <= 0:
            return RiskCheckResult(False, "Order quantity must be positive")

        return RiskCheckResult(True, "Quantity check passed")

    def check_order_notional(self, quantity: int, price: Decimal) -> RiskCheckResult:
        """
        Check if order notional value is within limits.

        Args:
            quantity: Order quantity
            price: Order price

        Returns:
            RiskCheckResult with pass/fail and reason
        """
        notional = abs(Decimal(quantity) * price)
        max_notional = self.config.max_order_notional

        if notional > max_notional:
            return RiskCheckResult(
                False,
                f"Order notional ${notional:.2f} exceeds limit ${max_notional:.2f}",
            )

        return RiskCheckResult(True, "Notional check passed")

    def check_positions_exposure(
        self, new_order_quantity: int, new_order_price: Decimal
    ) -> RiskCheckResult:
        """
        Check if adding a new order would exceed total positions exposure limit.

        Exposure = sum(abs(qty) * avg_entry_price) across all positions + new order notional

        Args:
            new_order_quantity: Quantity of new order
            new_order_price: Price of new order

        Returns:
            RiskCheckResult with pass/fail and reason
        """
        # Calculate current exposure from existing positions
        current_exposure = Decimal("0")
        for pos in self.positions.values():
            current_exposure += abs(pos.quantity) * pos.avg_price

        # Calculate new order notional
        new_order_notional = abs(Decimal(new_order_quantity) * new_order_price)

        # Total exposure after this order
        total_exposure = current_exposure + new_order_notional
        max_exposure = self.config.max_positions_notional

        if total_exposure > max_exposure:
            return RiskCheckResult(
                False,
                f"Total exposure ${total_exposure:.2f} (current: ${current_exposure:.2f} + "
                f"new: ${new_order_notional:.2f}) exceeds limit ${max_exposure:.2f}",
            )

        return RiskCheckResult(True, "Exposure check passed")

    def get_current_exposure(self) -> Decimal:
        """
        Get current total positions exposure.

        Returns:
            Total exposure across all positions
        """
        exposure = Decimal("0")
        for pos in self.positions.values():
            exposure += abs(pos.quantity) * pos.avg_price
        return exposure

    def update_position(self, symbol: str, quantity: int, price: Decimal):
        """
        Update position after a fill.

        Args:
            symbol: Symbol traded
            quantity: Quantity (positive for buy, negative for sell)
            price: Fill price
        """
        if symbol in self.positions:
            pos = self.positions[symbol]
            old_qty = pos.quantity
            new_qty = old_qty + quantity

            if new_qty == 0:
                # Position closed
                realized_pnl = (price - pos.avg_price) * abs(quantity)
                self.daily_pnl += realized_pnl
                del self.positions[symbol]
            elif new_qty > 0:
                # Adding to or reducing long position
                if old_qty > 0 and quantity > 0:
                    # Adding to long
                    total_cost = (pos.avg_price * old_qty) + (price * quantity)
                    pos.avg_price = total_cost / new_qty
                    pos.quantity = new_qty
                elif old_qty > 0 and quantity < 0:
                    # Reducing long
                    realized_pnl = (price - pos.avg_price) * abs(quantity)
                    self.daily_pnl += realized_pnl
                    pos.quantity = new_qty
                pos.update_price(price)
            else:
                # New short position or other complex case
                # For simplicity, we only support long positions in this MVP
                pass
        else:
            # New position
            if quantity > 0:
                self.positions[symbol] = Position(
                    symbol=symbol, quantity=quantity, avg_price=price, current_price=price
                )

    def get_positions(self) -> list[Position]:
        """Get all current positions."""
        return list(self.positions.values())

    def get_daily_pnl(self) -> Decimal:
        """Get daily realized PnL."""
        return self.daily_pnl

    def reset_daily_pnl(self):
        """Reset daily PnL (call at start of day)."""
        self.daily_pnl = Decimal("0")
