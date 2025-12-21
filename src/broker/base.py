"""Broker abstraction and implementations."""
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Optional, Set
import uuid

from src.app.models import Order, OrderSide, OrderType, OrderStatus


class Broker(ABC):
    """Abstract base class for broker implementations."""

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        client_order_id: str,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[Decimal] = None
    ) -> Order:
        """
        Submit an order to the broker.

        Args:
            symbol: Trading symbol
            side: Buy or sell
            quantity: Number of shares
            client_order_id: Client-generated order ID for idempotency
            order_type: Market or limit
            limit_price: Limit price (required for limit orders)

        Returns:
            Order object with initial status
        """
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Order:
        """
        Get current status of an order.

        Args:
            order_id: Order ID to check

        Returns:
            Order object with current status
        """
        pass

    @abstractmethod
    def get_open_orders(self) -> Set[str]:
        """
        Get set of client order IDs for all open orders.

        Returns:
            Set of client order IDs
        """
        pass

    @abstractmethod
    def order_exists(self, client_order_id: str) -> bool:
        """
        Check if an order with given client_order_id exists.

        Args:
            client_order_id: Client order ID to check

        Returns:
            True if order exists
        """
        pass


class MockBroker(Broker):
    """Mock broker for paper trading simulation."""

    def __init__(self):
        self.orders = {}  # broker_order_id -> Order
        self.client_order_map = {}  # client_order_id -> broker_order_id
        self.fill_delay = 0  # Instant fills for mock

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        client_order_id: str,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[Decimal] = None
    ) -> Order:
        """
        Submit a mock order that fills immediately.

        Args:
            symbol: Trading symbol
            side: Buy or sell
            quantity: Number of shares
            client_order_id: Client-generated order ID for idempotency
            order_type: Market or limit
            limit_price: Limit price (required for limit orders)

        Returns:
            Order object with filled status

        Raises:
            ValueError: If client_order_id already exists
        """
        # Check if order already exists
        if client_order_id in self.client_order_map:
            broker_order_id = self.client_order_map[client_order_id]
            existing_order = self.orders[broker_order_id]
            raise ValueError(f"Order with client_order_id {client_order_id} already exists")

        broker_order_id = str(uuid.uuid4())
        now = datetime.now()

        # Mock fill price (in real impl, would use current market price)
        fill_price = limit_price if limit_price else Decimal("100.00")

        order = Order(
            id=broker_order_id,
            symbol=symbol,
            side=side,
            type=order_type,
            quantity=quantity,
            price=limit_price,
            status=OrderStatus.FILLED,  # Mock orders fill immediately
            submitted_at=now,
            filled_at=now,
            filled_price=fill_price
        )

        self.orders[broker_order_id] = order
        self.client_order_map[client_order_id] = broker_order_id
        return order

    def get_order_status(self, order_id: str) -> Order:
        """
        Get order status from mock broker.

        Args:
            order_id: Broker order ID to check

        Returns:
            Order object

        Raises:
            KeyError: If order not found
        """
        return self.orders[order_id]

    def get_open_orders(self) -> Set[str]:
        """
        Get set of client order IDs for all open orders.

        Returns:
            Set of client order IDs
        """
        # Mock broker fills immediately, so no open orders
        # In real implementation, would filter by status
        return set()

    def order_exists(self, client_order_id: str) -> bool:
        """
        Check if an order with given client_order_id exists.

        Args:
            client_order_id: Client order ID to check

        Returns:
            True if order exists
        """
        return client_order_id in self.client_order_map


class AlpacaBroker(Broker):
    """Alpaca paper trading broker."""

    def __init__(self, api_key: str, secret_key: str, base_url: str):
        """
        Initialize Alpaca broker.

        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            base_url: Alpaca API base URL
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url

        # Note: In a real implementation, you would use the alpaca-py library here
        # For this MVP, we keep it simple and just store credentials
        # Actual implementation would import: from alpaca.trading import TradingClient

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        client_order_id: str,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[Decimal] = None
    ) -> Order:
        """
        Submit order to Alpaca.

        Args:
            symbol: Trading symbol
            side: Buy or sell
            quantity: Number of shares
            client_order_id: Client-generated order ID for idempotency
            order_type: Market or limit
            limit_price: Limit price (required for limit orders)

        Returns:
            Order object

        Note:
            This is a placeholder. Real implementation would use alpaca-py library:

            from alpaca.trading import TradingClient
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            client = TradingClient(self.api_key, self.secret_key, paper=True)
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                client_order_id=client_order_id
            )
            alpaca_order = client.submit_order(order_data)
            # Convert to our Order model...
        """
        raise NotImplementedError(
            "Alpaca broker requires alpaca-py library. "
            "Use MockBroker for offline testing."
        )

    def get_order_status(self, order_id: str) -> Order:
        """Get order status from Alpaca."""
        raise NotImplementedError(
            "Alpaca broker requires alpaca-py library. "
            "Use MockBroker for offline testing."
        )

    def get_open_orders(self) -> Set[str]:
        """Get open orders from Alpaca."""
        raise NotImplementedError(
            "Alpaca broker requires alpaca-py library. "
            "Use MockBroker for offline testing."
        )

    def order_exists(self, client_order_id: str) -> bool:
        """Check if order exists in Alpaca."""
        raise NotImplementedError(
            "Alpaca broker requires alpaca-py library. "
            "Use MockBroker for offline testing."
        )
