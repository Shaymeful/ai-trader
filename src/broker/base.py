"""Broker abstraction and implementations."""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from src.app.models import Order, OrderSide, OrderStatus, OrderType, Quote


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

    @abstractmethod
    def get_positions(self) -> dict[str, tuple[int, Decimal]]:
        """
        Get current positions from broker.

        Returns:
            Dictionary mapping symbol to (quantity, avg_price) tuples
        """
        pass

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        """
        Get current market quote for a symbol.

        Args:
            symbol: Symbol to get quote for

        Returns:
            Quote with bid/ask/last prices
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order by broker order ID.

        Args:
            order_id: Broker order ID to cancel

        Returns:
            True if cancellation succeeded
        """
        pass

    @abstractmethod
    def cancel_order_by_client_id(self, client_order_id: str) -> bool:
        """
        Cancel an order by client order ID.

        Args:
            client_order_id: Client order ID to cancel

        Returns:
            True if cancellation succeeded
        """
        pass

    @abstractmethod
    def replace_order(
        self, order_id: str, limit_price: Decimal, quantity: int | None = None
    ) -> Order:
        """
        Replace/modify an existing order.

        Args:
            order_id: Broker order ID to replace
            limit_price: New limit price
            quantity: New quantity (optional, keeps existing if None)

        Returns:
            New or modified Order object
        """
        pass

    @abstractmethod
    def list_open_orders_detailed(self) -> list[Order]:
        """
        Get detailed list of all open orders.

        Returns:
            List of Order objects for all open orders
        """
        pass


class MockBroker(Broker):
    """Mock broker for paper trading simulation."""

    def __init__(self):
        self.orders = {}  # broker_order_id -> Order
        self.client_order_map = {}  # client_order_id -> broker_order_id
        self.fill_delay = 0  # Instant fills for mock
        self.positions: dict[str, tuple[int, Decimal]] = {}  # symbol -> (qty, avg_price)

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

        # Update positions
        qty_change = quantity if side == OrderSide.BUY else -quantity
        if symbol in self.positions:
            old_qty, old_avg = self.positions[symbol]
            new_qty = old_qty + qty_change
            if new_qty == 0:
                del self.positions[symbol]
            elif new_qty > 0:
                if old_qty > 0 and qty_change > 0:
                    # Adding to position
                    new_avg = ((old_avg * old_qty) + (fill_price * quantity)) / new_qty
                    self.positions[symbol] = (new_qty, new_avg)
                else:
                    # Reducing position
                    self.positions[symbol] = (new_qty, old_avg)
        else:
            if qty_change > 0:
                self.positions[symbol] = (qty_change, fill_price)

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

    def get_positions(self) -> dict[str, tuple[int, Decimal]]:
        """
        Get current positions from mock broker.

        Returns:
            Dictionary mapping symbol to (quantity, avg_price) tuples
        """
        return self.positions.copy()

    def get_quote(self, symbol: str) -> Quote:
        """
        Get deterministic mock quote for a symbol.

        Uses most recent fill price or generates default quote.
        Spread is 0.1% (10 bps) for determinism.

        Args:
            symbol: Symbol to get quote for

        Returns:
            Quote with bid/ask/last prices
        """
        # Find last fill price for this symbol, or use default
        last_price = Decimal("100.00")  # Default
        for order in self.orders.values():
            if order.symbol == symbol and order.filled_price:
                last_price = order.filled_price

        # Create realistic spread: 0.1% (10 bps)
        spread_pct = Decimal("0.001")  # 0.1%
        half_spread = last_price * spread_pct / Decimal("2")

        return Quote(
            symbol=symbol,
            bid=last_price - half_spread,
            ask=last_price + half_spread,
            last=last_price,
            timestamp=datetime.now(),
        )

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order by broker order ID.

        Args:
            order_id: Broker order ID to cancel

        Returns:
            True if cancellation succeeded
        """
        if order_id not in self.orders:
            return False

        order = self.orders[order_id]
        if order.status == OrderStatus.FILLED:
            return False  # Cannot cancel filled order

        # Mark as canceled
        order.status = OrderStatus.CANCELED
        return True

    def cancel_order_by_client_id(self, client_order_id: str) -> bool:
        """
        Cancel an order by client order ID.

        Args:
            client_order_id: Client order ID to cancel

        Returns:
            True if cancellation succeeded
        """
        if client_order_id not in self.client_order_map:
            return False

        order_id = self.client_order_map[client_order_id]
        return self.cancel_order(order_id)

    def replace_order(
        self, order_id: str, limit_price: Decimal, quantity: int | None = None
    ) -> Order:
        """
        Replace/modify an existing order (mock implementation: cancel + new).

        Args:
            order_id: Broker order ID to replace
            limit_price: New limit price
            quantity: New quantity (optional, keeps existing if None)

        Returns:
            New Order object
        """
        if order_id not in self.orders:
            raise ValueError(f"Order {order_id} not found")

        old_order = self.orders[order_id]
        if old_order.status == OrderStatus.FILLED:
            raise ValueError("Cannot replace filled order")

        # Cancel old order
        old_order.status = OrderStatus.CANCELED

        # Create new order with same client_order_id pattern
        new_client_order_id = f"{old_order.symbol}-replace-{uuid.uuid4()}"
        new_quantity = quantity if quantity is not None else old_order.quantity

        return self.submit_order(
            symbol=old_order.symbol,
            side=old_order.side,
            quantity=new_quantity,
            client_order_id=new_client_order_id,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
        )

    def list_open_orders_detailed(self) -> list[Order]:
        """
        Get detailed list of all open orders.

        Returns:
            List of Order objects for all open orders
        """
        # Mock broker fills immediately, so return empty list
        # In real scenarios, would filter by pending status
        open_orders = []
        for order in self.orders.values():
            if order.status == OrderStatus.PENDING:
                open_orders.append(order)
        return open_orders


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
        from alpaca.trading.requests import GetOrdersRequest

        request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        open_orders = self.client.get_orders(filter=request)
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

    def get_positions(self) -> dict[str, tuple[int, Decimal]]:
        """
        Get current positions from Alpaca.

        Returns:
            Dictionary mapping symbol to (quantity, avg_price) tuples
        """
        positions_dict = {}
        try:
            positions = self.client.get_all_positions()
            for pos in positions:
                qty = int(pos.qty)
                avg_price = Decimal(str(pos.avg_entry_price))
                positions_dict[pos.symbol] = (qty, avg_price)
        except Exception:
            # If we can't get positions, return empty dict
            pass
        return positions_dict

    def get_quote(self, symbol: str) -> Quote:
        """
        Get current market quote from Alpaca.

        Args:
            symbol: Symbol to get quote for

        Returns:
            Quote with bid/ask/last prices
        """
        try:
            from alpaca.data import StockLatestQuoteRequest
            from alpaca.data.historical import StockHistoricalDataClient

            data_client = StockHistoricalDataClient(self.api_key, self.secret_key)
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quote_data = data_client.get_stock_latest_quote(request)
            q = quote_data[symbol]

            return Quote(
                symbol=symbol,
                bid=Decimal(str(q.bid_price)) if q.bid_price else Decimal("0"),
                ask=Decimal(str(q.ask_price)) if q.ask_price else Decimal("0"),
                last=Decimal(str(q.ask_price)) if q.ask_price else Decimal("0"),  # Use ask as proxy
                timestamp=datetime.now(),
            )
        except Exception:
            # Fallback to mock quote if Alpaca call fails
            # Use reasonable defaults
            return Quote(
                symbol=symbol,
                bid=Decimal("100.00"),
                ask=Decimal("100.10"),
                last=Decimal("100.05"),
                timestamp=datetime.now(),
            )

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order by broker order ID.

        Args:
            order_id: Broker order ID to cancel

        Returns:
            True if cancellation succeeded
        """
        try:
            from alpaca.trading.requests import CancelOrderResponse

            self.client.cancel_order_by_id(order_id)
            return True
        except Exception:
            return False

    def cancel_order_by_client_id(self, client_order_id: str) -> bool:
        """
        Cancel an order by client order ID.

        Args:
            client_order_id: Client order ID to cancel

        Returns:
            True if cancellation succeeded
        """
        try:
            # Alpaca supports canceling by client order ID
            # We need to get the order first, then cancel by ID
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus

            # Get all orders to find the one with matching client_order_id
            request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            orders = self.client.get_orders(filter=request)

            for order in orders:
                if order.client_order_id == client_order_id:
                    return self.cancel_order(str(order.id))

            return False
        except Exception:
            return False

    def replace_order(
        self, order_id: str, limit_price: Decimal, quantity: int | None = None
    ) -> Order:
        """
        Replace/modify an existing order using Alpaca's replace endpoint.

        Args:
            order_id: Broker order ID to replace
            limit_price: New limit price
            quantity: New quantity (optional, keeps existing if None)

        Returns:
            New Order object
        """
        try:
            from alpaca.trading.requests import ReplaceOrderRequest

            # Build replace request
            replace_params = {"limit_price": float(limit_price)}
            if quantity is not None:
                replace_params["qty"] = quantity

            request = ReplaceOrderRequest(**replace_params)
            new_order = self.client.replace_order_by_id(order_id, request)
            return self._convert_alpaca_order(new_order)
        except Exception as e:
            # If replace fails, fall back to cancel + new
            # Get the old order details first
            try:
                old_order_obj = self.client.get_order_by_id(order_id)
                old_order = self._convert_alpaca_order(old_order_obj)

                # Cancel old order
                self.cancel_order(order_id)

                # Create new order
                new_client_order_id = f"{old_order.symbol}-replace-{uuid.uuid4()}"
                new_quantity = quantity if quantity is not None else old_order.quantity

                return self.submit_order(
                    symbol=old_order.symbol,
                    side=old_order.side,
                    quantity=new_quantity,
                    client_order_id=new_client_order_id,
                    order_type=OrderType.LIMIT,
                    limit_price=limit_price,
                )
            except Exception as inner_e:
                raise ValueError(f"Failed to replace order: {inner_e}") from inner_e

    def list_open_orders_detailed(self) -> list[Order]:
        """
        Get detailed list of all open orders.

        Returns:
            List of Order objects for all open orders
        """
        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus

            request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            alpaca_orders = self.client.get_orders(filter=request)

            return [self._convert_alpaca_order(order) for order in alpaca_orders]
        except Exception:
            return []

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
