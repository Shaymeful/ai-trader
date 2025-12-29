"""Tests for execution layer."""

from decimal import Decimal

from src.app.config import Config
from src.app.execution import AlpacaExecutor
from src.app.models import OrderSide, OrderType
from src.broker import MockBroker


def test_executor_reconcile_buy_order():
    """Test executor generates buy order when target > current."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("5000"),
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=False)

    target_positions = {"SPY": 10}
    current_prices = {"SPY": Decimal("450.00")}

    # Current position is 0, target is 10 -> should buy 10
    result = executor.reconcile_and_execute(target_positions, current_prices)

    assert len(result.orders_placed) == 1
    assert len(result.orders_skipped) == 0
    assert result.total_risk_used > Decimal("0")


def test_executor_reconcile_sell_order():
    """Test executor generates sell order when target < current."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("5000"),
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    # Set current position
    broker.positions["SPY"] = (10, Decimal("440.00"))

    executor = AlpacaExecutor(broker, config, dry_run=False)

    target_positions = {"SPY": 5}
    current_prices = {"SPY": Decimal("450.00")}

    # Current position is 10, target is 5 -> should sell 5
    result = executor.reconcile_and_execute(target_positions, current_prices)

    assert len(result.orders_placed) == 1
    assert len(result.orders_skipped) == 0


def test_executor_reconcile_no_change():
    """Test executor skips order when target equals current."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("5000"),
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    broker.positions["SPY"] = (10, Decimal("440.00"))

    executor = AlpacaExecutor(broker, config, dry_run=False)

    target_positions = {"SPY": 10}
    current_prices = {"SPY": Decimal("450.00")}

    # Current position is 10, target is 10 -> no order
    result = executor.reconcile_and_execute(target_positions, current_prices)

    assert len(result.orders_placed) == 0
    assert len(result.orders_skipped) == 0


def test_executor_enforces_max_order_notional():
    """Test that executor enforces max_order_notional cap."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("1000"),  # Small cap
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=False)

    # Order would be 10 shares * $450 = $4500, exceeds $1000 cap
    target_positions = {"SPY": 10}
    current_prices = {"SPY": Decimal("450.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Order should be skipped due to cap
    assert len(result.orders_placed) == 0
    assert len(result.orders_skipped) == 1
    assert "exceeds max" in result.orders_skipped[0][1]


def test_executor_enforces_max_positions_notional():
    """Test that executor enforces max_positions_notional cap."""
    config = Config(
        max_positions_notional=Decimal("1000"),  # Small total cap
        max_order_notional=Decimal("5000"),
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    # Already have $900 exposure
    broker.positions["QQQ"] = (2, Decimal("450.00"))

    executor = AlpacaExecutor(broker, config, dry_run=False)

    # Want to add $4500 more, but would exceed total cap
    # Also keep QQQ in target to avoid unintended closes
    target_positions = {"SPY": 10, "QQQ": 2}
    current_prices = {"SPY": Decimal("450.00"), "QQQ": Decimal("450.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # SPY order should be skipped due to total exposure (QQQ already at target, no change)
    assert len(result.orders_placed) == 0
    assert len(result.orders_skipped) >= 1
    # Check that at least one skip reason mentions exceeding max
    assert any("would exceed" in reason for _, reason in result.orders_skipped)


def test_executor_dry_run_mode():
    """Test that dry_run mode doesn't place actual orders."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("5000"),
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=True)

    target_positions = {"SPY": 10}
    current_prices = {"SPY": Decimal("450.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should record as placed but not actually submit to broker
    assert len(result.orders_placed) == 1
    assert result.dry_run is True
    assert "DRY-RUN" in result.orders_placed[0]

    # Broker should have no orders
    assert len(broker.orders) == 0


def test_executor_uses_limit_orders():
    """Test that executor uses LIMIT orders with price offset."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("5000"),
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=False)

    target_positions = {"SPY": 10}
    current_prices = {"SPY": Decimal("450.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    assert len(result.orders_placed) == 1

    # Check that broker received a limit order
    assert len(broker.orders) == 1
    order = list(broker.orders.values())[0]
    assert order.type == OrderType.LIMIT
    assert order.price is not None
    # Buy order should have negative offset (more aggressive)
    assert order.price < Decimal("450.00")


def test_executor_missing_price():
    """Test that executor skips symbols with missing prices."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("5000"),
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=False)

    target_positions = {"SPY": 10}
    current_prices = {}  # No price for SPY

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should skip due to missing price
    # Note: The warning is logged in _generate_order_instructions
    assert len(result.orders_placed) == 0


def test_executor_flatten_position():
    """Test that executor can flatten a position (target=0)."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("5000"),
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    broker.positions["SPY"] = (10, Decimal("440.00"))

    executor = AlpacaExecutor(broker, config, dry_run=False)

    target_positions = {}  # Empty means we want to close all
    current_prices = {"SPY": Decimal("450.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should sell 10 shares to flatten
    assert len(result.orders_placed) == 1
    order = list(broker.orders.values())[0]
    assert order.side == OrderSide.SELL
    assert order.quantity == 10
