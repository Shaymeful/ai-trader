"""Core data models for the trading system."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, field_validator


class OrderSide(str, Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type."""

    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    """Order status."""

    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELED = "canceled"


class Bar(BaseModel):
    """Market data bar (OHLCV)."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    @field_validator("open", "high", "low", "close", mode="before")
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert numeric values to Decimal."""
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v


class Signal(BaseModel):
    """Trading signal from a strategy."""

    symbol: str
    side: OrderSide
    timestamp: datetime
    reason: str
    price: Decimal | None = None


class Order(BaseModel):
    """Trading order."""

    id: str
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: int
    price: Decimal | None = None
    status: OrderStatus = OrderStatus.PENDING
    submitted_at: datetime
    filled_at: datetime | None = None
    filled_price: Decimal | None = None
    rejected_reason: str | None = None


class Position(BaseModel):
    """Current position."""

    symbol: str
    quantity: int
    avg_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")

    def update_price(self, price: Decimal):
        """Update current price and recalculate PnL."""
        self.current_price = price
        self.unrealized_pnl = (price - self.avg_price) * self.quantity


class TradeRecord(BaseModel):
    """Trade record for CSV output."""

    timestamp: datetime
    symbol: str
    side: str
    quantity: int
    price: Decimal
    order_id: str
    client_order_id: str
    run_id: str
    reason: str

    def to_csv_row(self) -> str:
        """Convert to CSV row."""
        return f"{self.timestamp.isoformat()},{self.symbol},{self.side},{self.quantity},{self.price},{self.order_id},{self.client_order_id},{self.run_id},{self.reason}"

    @staticmethod
    def csv_header() -> str:
        """Return CSV header."""
        return "timestamp,symbol,side,quantity,price,order_id,client_order_id,run_id,reason"


class OrderRecord(BaseModel):
    """Order record for orders.csv."""

    timestamp: datetime
    symbol: str
    side: str
    quantity: int
    order_type: str
    limit_price: Decimal | None = None
    client_order_id: str
    broker_order_id: str
    run_id: str
    status: str

    def to_csv_row(self) -> str:
        """Convert to CSV row."""
        limit_price_str = str(self.limit_price) if self.limit_price else ""
        return f"{self.timestamp.isoformat()},{self.symbol},{self.side},{self.quantity},{self.order_type},{limit_price_str},{self.client_order_id},{self.broker_order_id},{self.run_id},{self.status}"

    @staticmethod
    def csv_header() -> str:
        """Return CSV header."""
        return "timestamp,symbol,side,quantity,order_type,limit_price,client_order_id,broker_order_id,run_id,status"


class FillRecord(BaseModel):
    """Fill record for fills.csv."""

    timestamp: datetime
    symbol: str
    side: str
    quantity: int
    price: Decimal
    client_order_id: str
    broker_order_id: str
    run_id: str

    def to_csv_row(self) -> str:
        """Convert to CSV row."""
        return f"{self.timestamp.isoformat()},{self.symbol},{self.side},{self.quantity},{self.price},{self.client_order_id},{self.broker_order_id},{self.run_id}"

    @staticmethod
    def csv_header() -> str:
        """Return CSV header."""
        return "timestamp,symbol,side,quantity,price,client_order_id,broker_order_id,run_id"
