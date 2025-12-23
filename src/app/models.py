"""Core data models for the trading system."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, field_validator


class Quote(BaseModel):
    """Market quote with bid/ask/last prices."""

    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    timestamp: datetime

    @property
    def mid(self) -> Decimal:
        """Calculate mid price."""
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        """Calculate bid-ask spread."""
        return self.ask - self.bid

    @property
    def spread_bps(self) -> Decimal:
        """Calculate spread in basis points."""
        if self.mid == 0:
            return Decimal("0")
        return (self.spread / self.mid) * Decimal("10000")

    def expected_entry_price(self, side: "OrderSide") -> Decimal:
        """
        Get expected entry price for given side.

        For BUY: expected to pay ask
        For SELL: expected to receive bid
        """
        from src.app.models import OrderSide

        return self.ask if side == OrderSide.BUY else self.bid


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
    # Cost tracking fields (optional for backward compatibility)
    expected_price: Decimal | None = None
    slippage_abs: Decimal | None = None
    slippage_bps: Decimal | None = None
    spread_bps_at_submit: Decimal | None = None

    def to_csv_row(self) -> str:
        """Convert to CSV row."""
        # Format optional fields, using empty string if None
        expected_price_str = str(self.expected_price) if self.expected_price is not None else ""
        slippage_abs_str = str(self.slippage_abs) if self.slippage_abs is not None else ""
        slippage_bps_str = str(self.slippage_bps) if self.slippage_bps is not None else ""
        spread_bps_str = (
            str(self.spread_bps_at_submit) if self.spread_bps_at_submit is not None else ""
        )

        return (
            f"{self.timestamp.isoformat()},{self.symbol},{self.side},{self.quantity},"
            f"{self.price},{self.order_id},{self.client_order_id},{self.run_id},{self.reason},"
            f"{expected_price_str},{slippage_abs_str},{slippage_bps_str},{spread_bps_str}"
        )

    @staticmethod
    def csv_header() -> str:
        """Return CSV header."""
        return (
            "timestamp,symbol,side,quantity,price,order_id,client_order_id,run_id,reason,"
            "expected_price,slippage_abs,slippage_bps,spread_bps_at_submit"
        )


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
    # Cost tracking fields (optional for backward compatibility)
    expected_price: Decimal | None = None
    slippage_abs: Decimal | None = None
    slippage_bps: Decimal | None = None
    spread_bps_at_submit: Decimal | None = None

    def to_csv_row(self) -> str:
        """Convert to CSV row."""
        # Format optional fields, using empty string if None
        expected_price_str = str(self.expected_price) if self.expected_price is not None else ""
        slippage_abs_str = str(self.slippage_abs) if self.slippage_abs is not None else ""
        slippage_bps_str = str(self.slippage_bps) if self.slippage_bps is not None else ""
        spread_bps_str = (
            str(self.spread_bps_at_submit) if self.spread_bps_at_submit is not None else ""
        )

        return (
            f"{self.timestamp.isoformat()},{self.symbol},{self.side},{self.quantity},"
            f"{self.price},{self.client_order_id},{self.broker_order_id},{self.run_id},"
            f"{expected_price_str},{slippage_abs_str},{slippage_bps_str},{spread_bps_str}"
        )

    @staticmethod
    def csv_header() -> str:
        """Return CSV header."""
        return (
            "timestamp,symbol,side,quantity,price,client_order_id,broker_order_id,run_id,"
            "expected_price,slippage_abs,slippage_bps,spread_bps_at_submit"
        )
