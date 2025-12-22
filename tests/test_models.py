"""Tests for data models."""

from datetime import datetime
from decimal import Decimal

from src.app.models import (
    Bar,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Signal,
    TradeRecord,
)


def test_bar_creation():
    """Test creating a Bar instance."""
    bar = Bar(
        symbol="AAPL",
        timestamp=datetime.now(),
        open=Decimal("100.50"),
        high=Decimal("101.00"),
        low=Decimal("100.00"),
        close=Decimal("100.75"),
        volume=1000000,
    )

    assert bar.symbol == "AAPL"
    assert bar.close == Decimal("100.75")


def test_bar_converts_float_to_decimal():
    """Test that Bar converts float prices to Decimal."""
    bar = Bar(
        symbol="MSFT",
        timestamp=datetime.now(),
        open=100.5,
        high=101.0,
        low=100.0,
        close=100.75,
        volume=500000,
    )

    assert isinstance(bar.close, Decimal)
    assert bar.close == Decimal("100.75")


def test_signal_creation():
    """Test creating a Signal instance."""
    signal = Signal(
        symbol="GOOGL", side=OrderSide.BUY, timestamp=datetime.now(), reason="Test signal"
    )

    assert signal.symbol == "GOOGL"
    assert signal.side == OrderSide.BUY


def test_order_creation():
    """Test creating an Order instance."""
    now = datetime.now()
    order = Order(
        id="123",
        symbol="TSLA",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=10,
        status=OrderStatus.PENDING,
        submitted_at=now,
    )

    assert order.symbol == "TSLA"
    assert order.quantity == 10
    assert order.status == OrderStatus.PENDING


def test_position_update_price():
    """Test updating position price and PnL."""
    pos = Position(
        symbol="AMZN", quantity=10, avg_price=Decimal("100"), current_price=Decimal("100")
    )

    pos.update_price(Decimal("110"))

    assert pos.current_price == Decimal("110")
    assert pos.unrealized_pnl == Decimal("100")  # 10 shares * $10 profit


def test_trade_record_csv_conversion():
    """Test converting TradeRecord to CSV format."""
    trade = TradeRecord(
        timestamp=datetime(2024, 1, 15, 10, 30),
        symbol="AAPL",
        side="buy",
        quantity=10,
        price=Decimal("150.50"),
        order_id="order-123",
        client_order_id="client-order-123",
        run_id="test-run-id",
        reason="Test trade",
    )

    csv_row = trade.to_csv_row()

    assert "AAPL" in csv_row
    assert "buy" in csv_row
    assert "150.50" in csv_row
    assert "client-order-123" in csv_row
    assert "test-run-id" in csv_row


def test_trade_record_csv_header():
    """Test CSV header format."""
    header = TradeRecord.csv_header()

    assert "timestamp" in header
    assert "symbol" in header
    assert "side" in header
    assert "quantity" in header
    assert "price" in header
    assert "client_order_id" in header
    assert "run_id" in header
