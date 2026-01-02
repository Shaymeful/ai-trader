"""Tests for broker module."""

from decimal import Decimal

import pytest

from src.app.models import OrderSide, OrderStatus, OrderType
from src.broker import MockBroker


@pytest.fixture
def broker():
    """Create mock broker instance."""
    return MockBroker()


def test_submit_market_order(broker):
    """Test submitting a market order."""
    order = broker.submit_order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        client_order_id="test-order-1",
        order_type=OrderType.MARKET,
    )

    assert order.symbol == "AAPL"
    assert order.side == OrderSide.BUY
    assert order.quantity == 10
    assert order.type == OrderType.MARKET
    assert order.status == OrderStatus.FILLED
    assert order.filled_price is not None


def test_submit_limit_order(broker):
    """Test submitting a limit order."""
    limit_price = Decimal("150.50")

    order = broker.submit_order(
        symbol="MSFT",
        side=OrderSide.SELL,
        quantity=5,
        client_order_id="test-order-2",
        order_type=OrderType.LIMIT,
        limit_price=limit_price,
    )

    assert order.symbol == "MSFT"
    assert order.side == OrderSide.SELL
    assert order.quantity == 5
    assert order.type == OrderType.LIMIT
    assert order.price == limit_price
    assert order.filled_price == limit_price


def test_get_order_status(broker):
    """Test retrieving order status."""
    order = broker.submit_order(
        symbol="GOOGL", side=OrderSide.BUY, quantity=20, client_order_id="test-order-3"
    )

    retrieved_order = broker.get_order_status(order.id)

    assert retrieved_order.id == order.id
    assert retrieved_order.symbol == order.symbol
    assert retrieved_order.status == order.status


def test_order_has_unique_id(broker):
    """Test that each order gets a unique broker ID."""
    order1 = broker.submit_order("AAPL", OrderSide.BUY, 10, "test-order-4")
    order2 = broker.submit_order("AAPL", OrderSide.BUY, 10, "test-order-5")

    assert order1.id != order2.id


def test_mock_broker_stores_orders(broker):
    """Test that mock broker stores all orders."""
    order1 = broker.submit_order("AAPL", OrderSide.BUY, 10, "test-order-6")
    order2 = broker.submit_order("MSFT", OrderSide.SELL, 5, "test-order-7")

    assert len(broker.orders) == 2
    assert order1.id in broker.orders
    assert order2.id in broker.orders


def test_broker_rejects_duplicate_client_order_id(broker):
    """Test that broker rejects duplicate client_order_id."""
    client_id = "test-duplicate-order"

    # First submission should succeed
    order1 = broker.submit_order("AAPL", OrderSide.BUY, 10, client_id)
    assert order1 is not None

    # Second submission with same client_order_id should fail
    with pytest.raises(ValueError, match="already exists"):
        broker.submit_order("AAPL", OrderSide.BUY, 10, client_id)


def test_broker_order_exists(broker):
    """Test order_exists method."""
    client_id = "test-exists-order"

    assert not broker.order_exists(client_id)

    broker.submit_order("AAPL", OrderSide.BUY, 10, client_id)

    assert broker.order_exists(client_id)


def test_broker_get_open_orders(broker):
    """Test get_open_orders method."""
    # Mock broker fills immediately, so no open orders
    open_orders = broker.get_open_orders()
    assert len(open_orders) == 0


def test_fractional_buy_market_order(broker):
    """Test submitting fractional buy market order."""
    order = broker.submit_order(
        symbol="SPY",
        side=OrderSide.BUY,
        quantity=0.164,  # Fractional quantity
        client_order_id="test-fractional-buy",
        order_type=OrderType.MARKET,
    )

    assert order.symbol == "SPY"
    assert order.side == OrderSide.BUY
    assert order.quantity == 0.164
    assert order.type == OrderType.MARKET
    assert order.status == OrderStatus.FILLED
    assert order.filled_price is not None


def test_fractional_sell_market_order(broker):
    """Test submitting fractional sell market order."""
    order = broker.submit_order(
        symbol="SPY",
        side=OrderSide.SELL,
        quantity=0.223,  # Fractional quantity
        client_order_id="test-fractional-sell",
        order_type=OrderType.MARKET,
    )

    assert order.symbol == "SPY"
    assert order.side == OrderSide.SELL
    assert order.quantity == 0.223
    assert order.type == OrderType.MARKET
    assert order.status == OrderStatus.FILLED
    assert order.filled_price is not None


def test_fractional_limit_order(broker):
    """Test submitting fractional limit order."""
    limit_price = Decimal("450.00")

    order = broker.submit_order(
        symbol="SPY",
        side=OrderSide.BUY,
        quantity=0.5,  # Fractional quantity
        client_order_id="test-fractional-limit",
        order_type=OrderType.LIMIT,
        limit_price=limit_price,
    )

    assert order.symbol == "SPY"
    assert order.side == OrderSide.BUY
    assert order.quantity == 0.5
    assert order.type == OrderType.LIMIT
    assert order.price == limit_price


def test_whole_share_order_uses_int(broker):
    """Test that whole share orders maintain integer quantities."""
    order = broker.submit_order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=10,  # Whole number
        client_order_id="test-whole-shares",
        order_type=OrderType.MARKET,
    )

    assert order.symbol == "AAPL"
    assert order.quantity == 10
    assert isinstance(order.quantity, int)


def test_cancel_all_open_orders_empty(broker):
    """Test cancel_all_open_orders when no orders exist."""
    canceled_count = broker.cancel_all_open_orders()
    assert canceled_count == 0


def test_cancel_all_open_orders_filled(broker):
    """Test cancel_all_open_orders when all orders are filled."""
    # MockBroker fills orders immediately
    broker.submit_order("AAPL", OrderSide.BUY, 10, "test-filled-1")
    broker.submit_order("MSFT", OrderSide.BUY, 5, "test-filled-2")

    # No pending orders to cancel
    canceled_count = broker.cancel_all_open_orders()
    assert canceled_count == 0
