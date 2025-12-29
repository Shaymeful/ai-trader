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
    """Test that executor slices orders exceeding max_order_notional cap."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("1000"),  # Cap allows ~2 shares at $450
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=False)

    # Order would be 10 shares * $450 = $4500, exceeds $1000 cap
    # Should be sliced into multiple orders
    target_positions = {"SPY": 10}
    current_prices = {"SPY": Decimal("450.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Order should be sliced (not skipped)
    assert len(result.orders_placed) > 1  # Multiple slices
    assert len(result.orders_skipped) == 0

    # Verify total quantity matches target
    total_qty = sum(order.quantity for order in broker.orders.values())
    assert total_qty == 10


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


def test_executor_slices_large_order():
    """Test that executor slices orders exceeding max_order_notional."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("200"),  # Cap allows ~3 shares at $55
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=False)

    # Want to buy 5 shares of XLF at $55 = $275, should be sliced
    # With $200 cap and price $55, can fit 3 shares per slice
    target_positions = {"XLF": 5}
    current_prices = {"XLF": Decimal("55.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should place multiple orders (sliced)
    # First slice: 3 shares, second slice: 2 shares
    assert len(result.orders_placed) >= 2
    assert len(result.orders_skipped) == 0

    # Verify total quantity matches target
    total_qty = sum(order.quantity for order in broker.orders.values())
    assert total_qty == 5


def test_executor_risk_reducing_sell_with_slicing():
    """Test that risk-reducing sells proceed even when exceeding max_order_notional."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("100"),  # Small cap
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    # Have 2 shares of SPY at $690 each = $1380 exposure
    broker.positions["SPY"] = (2, Decimal("680.00"))

    executor = AlpacaExecutor(broker, config, dry_run=False)

    # Target = 0 (flatten), should SELL 2 shares
    # Notional = 2 * $690 = $1380 > $100 cap
    # But this is risk-reducing, so should slice and proceed
    target_positions = {}  # Empty means flatten to 0
    current_prices = {"SPY": Decimal("690.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should place 2 sell orders (1 share each, sliced)
    assert len(result.orders_placed) == 2
    assert len(result.orders_skipped) == 0

    # Check that all orders are SELL orders
    for order in broker.orders.values():
        assert order.side == OrderSide.SELL


def test_executor_partial_flatten_with_slicing():
    """Test executor can partially reduce position with order slicing."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("150"),  # Can fit ~1 share at $690
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    broker.positions["SPY"] = (5, Decimal("680.00"))

    executor = AlpacaExecutor(broker, config, dry_run=False)

    # Want to reduce from 5 to 1
    target_positions = {"SPY": 1}
    current_prices = {"SPY": Decimal("690.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should SELL 4 shares (delta = 1 - 5 = -4)
    # With cap $150 and price ~$690, should slice into 4 orders of 1 share each
    assert len(result.orders_placed) == 4
    assert len(result.orders_skipped) == 0

    # Verify final position is 1
    final_position = broker.positions.get("SPY", (0, Decimal("0")))[0]
    assert final_position == 1


def test_executor_buy_order_slicing():
    """Test that BUY orders are also sliced when exceeding cap."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("300"),  # Can fit ~1 share at $273
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=False)

    # Want to buy 3 shares of AAPL at $273
    target_positions = {"AAPL": 3}
    current_prices = {"AAPL": Decimal("273.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should slice into 3 orders of 1 share each
    assert len(result.orders_placed) == 3
    assert len(result.orders_skipped) == 0

    # Verify all are BUY orders
    for order in broker.orders.values():
        assert order.side == OrderSide.BUY


def test_executor_mixed_slicing_and_no_slicing():
    """Test executor handles mix of sliced and non-sliced orders."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("300"),  # Increased cap to allow slicing
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=False)

    # XLF: cheap stock, can fit within cap (no slicing needed)
    # AAPL: moderate price, needs slicing (3 shares at $273 = $819, but can fit 1 share per slice)
    target_positions = {"XLF": 1, "AAPL": 3}
    current_prices = {"XLF": Decimal("55.00"), "AAPL": Decimal("273.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # XLF: 1 order (no slicing needed, $55 < $300)
    # AAPL: 3 orders (sliced into 1 share each, $273 < $300 per slice)
    # Total: 4 orders
    assert len(result.orders_placed) == 4
    assert len(result.orders_skipped) == 0


def test_executor_skips_buy_when_single_share_exceeds_cap():
    """Test that BUY orders are skipped when single share exceeds max_order_usd."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("100"),  # Cap is $100
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=False)

    # Want to buy 1 share of SPY at $690 = $690 > $100 cap
    # Since qty=1 (atomic unit), cannot slice further, must skip
    target_positions = {"SPY": 1}
    current_prices = {"SPY": Decimal("690.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should skip because single share exceeds cap
    assert len(result.orders_placed) == 0
    assert len(result.orders_skipped) == 1
    assert result.orders_skipped[0][0] == "SPY"
    assert "cannot be sliced" in result.orders_skipped[0][1]


def test_executor_skips_buy_in_dry_run_when_single_share_exceeds_cap():
    """Test that dry-run mode also skips BUY orders when single share exceeds cap."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("100"),  # Cap is $100
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=True)  # DRY-RUN mode

    # Want to buy 1 share of SPY at $690 = $690 > $100 cap
    target_positions = {"SPY": 1}
    current_prices = {"SPY": Decimal("690.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Dry-run should have SAME enforcement as live mode
    assert len(result.orders_placed) == 0
    assert len(result.orders_skipped) == 1
    assert result.orders_skipped[0][0] == "SPY"
    assert "cannot be sliced" in result.orders_skipped[0][1]
    assert result.dry_run is True


def test_executor_allows_risk_reducing_sell_even_if_single_share_exceeds_cap():
    """Test that risk-reducing sells proceed even when single share exceeds cap."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("100"),  # Cap is $100
        max_daily_loss=Decimal("500"),
    )

    broker = MockBroker()
    # Have 1 share of expensive stock
    broker.positions["SPY"] = (1, Decimal("680.00"))

    executor = AlpacaExecutor(broker, config, dry_run=False)

    # Target = 0 (flatten), should SELL 1 share
    # Notional = 1 * $690 = $690 > $100 cap
    # But this is risk-reducing, so should proceed (allows exits)
    target_positions = {}  # Empty means flatten to 0
    current_prices = {"SPY": Decimal("690.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should place the sell order (risk-reducing exception)
    assert len(result.orders_placed) == 1
    assert len(result.orders_skipped) == 0

    # Verify it's a SELL order
    order = list(broker.orders.values())[0]
    assert order.side == OrderSide.SELL
    assert order.quantity == 1


def test_executor_fractional_shares_when_enabled():
    """Test that fractional shares are used when allow_fractional=True."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("100"),  # Cap is $100
        max_daily_loss=Decimal("500"),
        allow_fractional=True,  # Enable fractional shares
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=False)

    # Want to buy 1 share of SPY at $690 = $690 > $100 cap
    # With fractional enabled, should place fractional order
    target_positions = {"SPY": 1}
    current_prices = {"SPY": Decimal("690.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should place 1 fractional order
    assert len(result.orders_placed) == 1
    assert len(result.orders_skipped) == 0

    # Verify fractional quantity
    order = list(broker.orders.values())[0]
    assert order.side == OrderSide.BUY
    assert isinstance(order.quantity, float)
    # With limit price offset (-0.5%), effective price is ~$686.55
    # Max qty = 100 / 686.55 ≈ 0.145, rounded to 0.145
    assert 0.140 < order.quantity < 0.150


def test_executor_fractional_shares_dry_run():
    """Test that fractional shares work correctly in dry-run mode."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("100"),
        max_daily_loss=Decimal("500"),
        allow_fractional=True,
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=True)  # DRY-RUN

    target_positions = {"SPY": 1}
    current_prices = {"SPY": Decimal("690.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should show fractional order in dry-run
    assert len(result.orders_placed) == 1
    assert len(result.orders_skipped) == 0
    assert result.dry_run is True


def test_executor_fractional_shares_multiple_symbols():
    """Test fractional shares with multiple expensive symbols."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("100"),
        max_daily_loss=Decimal("500"),
        allow_fractional=True,
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=False)

    # Both symbols exceed cap, should get fractional orders for both
    target_positions = {"SPY": 1, "QQQ": 1}
    current_prices = {"SPY": Decimal("690.00"), "QQQ": Decimal("500.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should place 2 fractional orders
    assert len(result.orders_placed) == 2
    assert len(result.orders_skipped) == 0

    # Both should be fractional
    for order in broker.orders.values():
        assert isinstance(order.quantity, float)
        assert order.quantity < 1.0


def test_executor_fractional_disabled_shows_helpful_message():
    """Test that skip message suggests enabling fractional when disabled."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("100"),
        max_daily_loss=Decimal("500"),
        allow_fractional=False,  # Disabled
    )

    broker = MockBroker()
    executor = AlpacaExecutor(broker, config, dry_run=False)

    target_positions = {"SPY": 1}
    current_prices = {"SPY": Decimal("690.00")}

    result = executor.reconcile_and_execute(target_positions, current_prices)

    # Should skip with helpful message
    assert len(result.orders_placed) == 0
    assert len(result.orders_skipped) == 1
    assert "allow_fractional" in result.orders_skipped[0][1]
