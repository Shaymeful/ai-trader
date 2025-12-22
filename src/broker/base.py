"""Broker abstraction and implementations."""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from src.app.models import Order, OrderSide, OrderStatus, OrderType


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
        limit_price: Decimal | None = None,
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
    def get_open_orders(self) -> set[str]:
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
        limit_price: Decimal | None = None,
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
            filled_price=fill_price,
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

    def get_open_orders(self) -> set[str]:
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

        # Initialize Alpaca trading client
        from alpaca.trading import TradingClient

        # Determine if paper trading based on base_url
        is_paper = "paper" in base_url.lower()
        self.client = TradingClient(api_key, secret_key, paper=is_paper)

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        client_order_id: str,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Decimal | None = None,
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
        """
        from alpaca.trading.enums import OrderSide as AlpacaOrderSide
        from alpaca.trading.enums import TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        # Convert our OrderSide to Alpaca's OrderSide
        alpaca_side = AlpacaOrderSide.BUY if side == OrderSide.BUY else AlpacaOrderSide.SELL

        # Submit order based on type
        if order_type == OrderType.MARKET:
            order_request = MarketOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=alpaca_side,
                time_in_force=TimeInForce.DAY,
                client_order_id=client_order_id,
            )
        else:  # LIMIT
            if limit_price is None:
                raise ValueError("Limit price required for limit orders")
            order_request = LimitOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=alpaca_side,
                time_in_force=TimeInForce.DAY,
                limit_price=float(limit_price),
                client_order_id=client_order_id,
            )

        # Submit to Alpaca
        alpaca_order = self.client.submit_order(order_request)

        # Convert to our Order model
        return self._convert_alpaca_order(alpaca_order)

    def get_order_status(self, order_id: str) -> Order:
        """
        Get order status from Alpaca.

        Args:
            order_id: Alpaca order ID

        Returns:
            Order object with current status
        """
        alpaca_order = self.client.get_order_by_id(order_id)
        return self._convert_alpaca_order(alpaca_order)

    def get_open_orders(self) -> set[str]:
        """
        Get set of client order IDs for all open orders.

        Returns:
            Set of client order IDs
        """
        from alpaca.trading.enums import QueryOrderStatus

        open_orders = self.client.get_orders(filter=QueryOrderStatus.OPEN)
        return {order.client_order_id for order in open_orders if order.client_order_id}

    def order_exists(self, client_order_id: str) -> bool:
        """
        Check if order exists in Alpaca.

        Args:
            client_order_id: Client order ID to check

        Returns:
            True if order exists
        """
        try:
            self.client.get_order_by_client_id(client_order_id)
            return True
        except Exception:
            return False

    def _convert_alpaca_order(self, alpaca_order) -> Order:
        """
        Convert Alpaca order to our Order model.

        Args:
            alpaca_order: Alpaca order object

        Returns:
            Our Order model
        """
        from alpaca.trading.enums import OrderStatus as AlpacaOrderStatus

        # Map Alpaca status to our status
        status_map = {
            AlpacaOrderStatus.NEW: OrderStatus.PENDING,
            AlpacaOrderStatus.ACCEPTED: OrderStatus.PENDING,
            AlpacaOrderStatus.PARTIALLY_FILLED: OrderStatus.PENDING,
            AlpacaOrderStatus.FILLED: OrderStatus.FILLED,
            AlpacaOrderStatus.CANCELED: OrderStatus.CANCELED,
            AlpacaOrderStatus.REJECTED: OrderStatus.REJECTED,
            AlpacaOrderStatus.EXPIRED: OrderStatus.CANCELED,
        }

        status = status_map.get(alpaca_order.status, OrderStatus.PENDING)

        # Map Alpaca side to our side
        our_side = OrderSide.BUY if alpaca_order.side.name == "BUY" else OrderSide.SELL

        # Map Alpaca order type to our type
        our_type = OrderType.MARKET if alpaca_order.type.name == "MARKET" else OrderType.LIMIT

        # Get filled info if available
        filled_at = None
        filled_price = None
        if alpaca_order.filled_at:
            filled_at = alpaca_order.filled_at.replace(tzinfo=None)
        if alpaca_order.filled_avg_price:
            filled_price = Decimal(str(alpaca_order.filled_avg_price))

        # Get submitted time
        submitted_at = alpaca_order.submitted_at.replace(tzinfo=None)

        return Order(
            id=str(alpaca_order.id),
            symbol=alpaca_order.symbol,
            side=our_side,
            type=our_type,
            quantity=int(alpaca_order.qty),
            price=Decimal(str(alpaca_order.limit_price)) if alpaca_order.limit_price else None,
            status=status,
            submitted_at=submitted_at,
            filled_at=filled_at,
            filled_price=filled_price,
        )
