"""Tests for reconciliation module."""

from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from src.app.config import Config
from src.app.models import Position
from src.app.reconciliation import reconcile_with_broker
from src.app.state import BotState
from src.broker import MockBroker
from src.broker.base import AlpacaBroker
from src.risk import RiskManager


@pytest.fixture
def config():
    """Create test configuration."""
    return Config(
        mode="mock",
        allowed_symbols=["AAPL", "MSFT"],
        max_positions=2,
        max_order_quantity=100,
        max_daily_loss=Decimal("1000"),
    )


@pytest.fixture
def broker():
    """Create mock broker instance."""
    return MockBroker()


@pytest.fixture
def state():
    """Create bot state instance."""
    return BotState(
        run_id="test-run", submitted_client_order_ids=set(), last_processed_timestamp={}
    )


@pytest.fixture
def risk_manager(config):
    """Create risk manager instance."""
    return RiskManager(config)


def test_reconcile_empty_broker_and_state(config, broker, state, risk_manager):
    """Test reconciliation when broker and state are both empty."""
    result = reconcile_with_broker(config, broker, state, risk_manager)

    assert result.broker_open_orders_count == 0
    assert result.local_orders_added == 0
    assert result.broker_positions_count == 0
    assert result.positions_synced == 0
    assert result.positions_added == 0
    assert result.positions_removed == 0
    assert len(state.submitted_client_order_ids) == 0
    assert len(risk_manager.positions) == 0


def test_reconcile_broker_has_orders_state_empty(config, broker, state, risk_manager):
    """Test reconciliation when broker has orders but state is empty."""
    # Simulate broker having open orders
    broker_orders = {"order-1", "order-2", "order-3"}
    broker.get_open_orders = lambda: broker_orders

    result = reconcile_with_broker(config, broker, state, risk_manager)

    assert result.broker_open_orders_count == 3
    assert result.local_orders_added == 3
    assert state.submitted_client_order_ids == broker_orders


def test_reconcile_state_has_orders_broker_empty(config, broker, state, risk_manager):
    """Test reconciliation when state has orders but broker doesn't."""
    # State has orders
    state.submitted_client_order_ids = {"order-1", "order-2"}

    # Broker has no orders
    broker.get_open_orders = lambda: set()

    result = reconcile_with_broker(config, broker, state, risk_manager)

    assert result.broker_open_orders_count == 0
    assert result.local_orders_added == 0
    # Orders are NOT removed from state (idempotency protection)
    assert len(state.submitted_client_order_ids) == 2
    assert state.submitted_client_order_ids == {"order-1", "order-2"}


def test_reconcile_partial_overlap_orders(config, broker, state, risk_manager):
    """Test reconciliation when broker and state have partial overlap."""
    # State has some orders
    state.submitted_client_order_ids = {"order-1", "order-2", "order-3"}

    # Broker has different set (some overlap, some new)
    broker_orders = {"order-2", "order-3", "order-4", "order-5"}
    broker.get_open_orders = lambda: broker_orders

    result = reconcile_with_broker(config, broker, state, risk_manager)

    assert result.broker_open_orders_count == 4
    assert result.local_orders_added == 2  # order-4, order-5
    # State should have union of both (order-1 remains for idempotency)
    assert state.submitted_client_order_ids == {
        "order-1",
        "order-2",
        "order-3",
        "order-4",
        "order-5",
    }


def test_reconcile_broker_has_positions_risk_manager_empty(config, broker, state, risk_manager):
    """Test reconciliation when broker has positions but risk manager doesn't."""
    # Broker has positions
    broker_positions = {
        "AAPL": (100, Decimal("150.50")),
        "MSFT": (50, Decimal("300.25")),
    }
    broker.get_positions = lambda: broker_positions

    result = reconcile_with_broker(config, broker, state, risk_manager)

    assert result.broker_positions_count == 2
    assert result.positions_added == 2
    assert result.positions_synced == 0
    assert result.positions_removed == 0
    assert len(risk_manager.positions) == 2
    assert "AAPL" in risk_manager.positions
    assert "MSFT" in risk_manager.positions
    assert risk_manager.positions["AAPL"].quantity == 100
    assert risk_manager.positions["AAPL"].avg_price == Decimal("150.50")


def test_reconcile_risk_manager_has_positions_broker_empty(config, broker, state, risk_manager):
    """Test reconciliation when risk manager has positions but broker doesn't."""
    # Risk manager has positions
    risk_manager.positions = {
        "AAPL": Position(
            symbol="AAPL",
            quantity=100,
            avg_price=Decimal("150.50"),
            current_price=Decimal("150.50"),
        ),
        "MSFT": Position(
            symbol="MSFT", quantity=50, avg_price=Decimal("300.25"), current_price=Decimal("300.25")
        ),
    }

    # Broker has no positions
    broker.get_positions = lambda: {}

    result = reconcile_with_broker(config, broker, state, risk_manager)

    assert result.broker_positions_count == 0
    assert result.positions_added == 0
    assert result.positions_synced == 0
    assert result.positions_removed == 2
    assert len(risk_manager.positions) == 0


def test_reconcile_positions_need_sync(config, broker, state, risk_manager):
    """Test reconciliation when positions exist but have different quantities."""
    # Risk manager has positions with old data
    risk_manager.positions = {
        "AAPL": Position(
            symbol="AAPL",
            quantity=100,
            avg_price=Decimal("150.50"),
            current_price=Decimal("150.50"),
        ),
        "MSFT": Position(
            symbol="MSFT", quantity=50, avg_price=Decimal("300.25"), current_price=Decimal("300.25")
        ),
    }

    # Broker has updated positions
    broker_positions = {
        "AAPL": (150, Decimal("155.00")),  # Increased quantity, different avg price
        "MSFT": (50, Decimal("300.25")),  # Same
    }
    broker.get_positions = lambda: broker_positions

    result = reconcile_with_broker(config, broker, state, risk_manager)

    assert result.broker_positions_count == 2
    assert result.positions_added == 0
    assert result.positions_synced == 1  # AAPL was synced
    assert result.positions_removed == 0
    assert risk_manager.positions["AAPL"].quantity == 150
    assert risk_manager.positions["AAPL"].avg_price == Decimal("155.00")


def test_reconcile_partial_overlap_positions(config, broker, state, risk_manager):
    """Test reconciliation when broker and risk manager have partial overlap in positions."""
    # Risk manager has some positions
    risk_manager.positions = {
        "AAPL": Position(
            symbol="AAPL",
            quantity=100,
            avg_price=Decimal("150.50"),
            current_price=Decimal("150.50"),
        ),
        "GOOGL": Position(
            symbol="GOOGL",
            quantity=25,
            avg_price=Decimal("2800.00"),
            current_price=Decimal("2800.00"),
        ),
    }

    # Broker has different set
    broker_positions = {
        "AAPL": (100, Decimal("150.50")),  # Same
        "MSFT": (50, Decimal("300.25")),  # New
    }
    broker.get_positions = lambda: broker_positions

    result = reconcile_with_broker(config, broker, state, risk_manager)

    assert result.broker_positions_count == 2
    assert result.positions_added == 1  # MSFT added
    assert result.positions_synced == 0  # AAPL matches
    assert result.positions_removed == 1  # GOOGL removed
    assert len(risk_manager.positions) == 2
    assert "AAPL" in risk_manager.positions
    assert "MSFT" in risk_manager.positions
    assert "GOOGL" not in risk_manager.positions


def test_reconcile_without_risk_manager(config, broker, state):
    """Test reconciliation when risk_manager is None (only reconcile orders)."""
    # Broker has orders and positions
    broker_orders = {"order-1", "order-2"}
    broker.get_open_orders = lambda: broker_orders

    broker_positions = {"AAPL": (100, Decimal("150.50"))}
    broker.get_positions = lambda: broker_positions

    result = reconcile_with_broker(config, broker, state, risk_manager=None)

    # Orders should be reconciled
    assert result.broker_open_orders_count == 2
    assert result.local_orders_added == 2
    assert state.submitted_client_order_ids == broker_orders

    # Positions should not be reconciled (counts remain 0)
    assert result.broker_positions_count == 0
    assert result.positions_added == 0
    assert result.positions_synced == 0
    assert result.positions_removed == 0


def test_reconcile_handles_broker_errors(config, broker, state, risk_manager):
    """Test that reconciliation handles broker errors gracefully."""

    # Make broker methods raise exceptions
    def raise_error():
        raise Exception("Broker connection error")

    broker.get_open_orders = raise_error
    broker.get_positions = raise_error

    # Should not raise, should handle gracefully
    result = reconcile_with_broker(config, broker, state, risk_manager)

    # Should have attempted but gotten 0 results due to errors
    assert result.broker_open_orders_count == 0
    assert result.broker_positions_count == 0


def test_alpaca_broker_get_open_orders_uses_correct_request():
    """Test that AlpacaBroker.get_open_orders uses GetOrdersRequest correctly."""
    # Create AlpacaBroker with dummy credentials
    with patch("alpaca.trading.TradingClient") as mock_trading_client_class:
        mock_client = Mock()
        mock_trading_client_class.return_value = mock_client

        broker = AlpacaBroker(
            api_key="test_key",
            secret_key="test_secret",
            base_url="https://paper-api.alpaca.markets",
        )

        # Mock the orders response
        mock_order1 = Mock()
        mock_order1.client_order_id = "order-1"
        mock_order2 = Mock()
        mock_order2.client_order_id = "order-2"
        mock_order3 = Mock()
        mock_order3.client_order_id = None  # Some orders might not have client_order_id

        mock_client.get_orders.return_value = [mock_order1, mock_order2, mock_order3]

        # Call get_open_orders
        result = broker.get_open_orders()

        # Verify it called get_orders with a GetOrdersRequest
        assert mock_client.get_orders.called
        call_args = mock_client.get_orders.call_args

        # Check that filter parameter was passed
        assert "filter" in call_args.kwargs

        # The filter should be a GetOrdersRequest with status=QueryOrderStatus.OPEN
        from alpaca.trading.requests import GetOrdersRequest

        request = call_args.kwargs["filter"]
        assert isinstance(request, GetOrdersRequest)

        # Verify the result contains only orders with client_order_ids
        assert result == {"order-1", "order-2"}
        assert "order-3" not in result  # Should be filtered out
