"""Tests for allocator module."""

from decimal import Decimal

from src.app.allocator import Allocator
from src.app.config import Config
from src.app.strategies import PositionIntent


def test_allocator_equal_weight():
    """Test that allocator divides capital equally across strategies."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("5000"),  # High enough to not cap individual orders
        max_daily_loss=Decimal("500"),
    )

    allocator = Allocator(config)

    # Two strategies with simple intents
    strategy_intents = {
        "strategy_a": [
            PositionIntent(symbol="SPY", target_quantity=10, conviction=0.8, reason="test"),
        ],
        "strategy_b": [
            PositionIntent(symbol="QQQ", target_quantity=5, conviction=0.6, reason="test"),
        ],
    }

    current_prices = {
        "SPY": Decimal("450.00"),
        "QQQ": Decimal("380.00"),
    }

    result = allocator.allocate(strategy_intents, current_prices)

    # Each strategy should get $5000 budget
    assert result.strategy_budgets["strategy_a"] == Decimal("5000")
    assert result.strategy_budgets["strategy_b"] == Decimal("5000")

    # Target positions should be aggregated
    assert "SPY" in result.target_positions
    assert "QQQ" in result.target_positions
    assert result.target_positions["SPY"] == 10
    assert result.target_positions["QQQ"] == 5


def test_allocator_risk_cap_per_order():
    """Test that allocator enforces max_order_notional cap."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("500"),  # Small cap
        max_daily_loss=Decimal("500"),
    )

    allocator = Allocator(config)

    strategy_intents = {
        "strategy_a": [
            # 10 shares * $450 = $4500 > $500 cap, should be reduced
            PositionIntent(symbol="SPY", target_quantity=10, conviction=0.8, reason="test"),
        ],
    }

    current_prices = {
        "SPY": Decimal("450.00"),
    }

    result = allocator.allocate(strategy_intents, current_prices)

    # Should be capped to 1 share ($450 < $500)
    assert result.target_positions["SPY"] == 1
    assert len(result.warnings) > 0
    assert "Capped" in result.warnings[0]


def test_allocator_risk_cap_total_notional():
    """Test that allocator enforces max_positions_notional cap."""
    config = Config(
        max_positions_notional=Decimal("1000"),  # Small total cap
        max_order_notional=Decimal("500"),
        max_daily_loss=Decimal("500"),
    )

    allocator = Allocator(config)

    strategy_intents = {
        "strategy_a": [
            PositionIntent(symbol="SPY", target_quantity=5, conviction=0.8, reason="test"),
            PositionIntent(symbol="QQQ", target_quantity=5, conviction=0.6, reason="test"),
        ],
    }

    current_prices = {
        "SPY": Decimal("450.00"),  # 5 shares = $2250
        "QQQ": Decimal("380.00"),  # 5 shares = $1900
    }

    result = allocator.allocate(strategy_intents, current_prices)

    # Total notional should not exceed $1000
    total_notional = sum(
        abs(qty) * current_prices[symbol] for symbol, qty in result.target_positions.items()
    )
    assert total_notional <= Decimal("1000")
    assert len(result.warnings) > 0  # Should have warnings about skipped/reduced positions


def test_allocator_missing_prices():
    """Test that allocator handles missing prices gracefully."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("1000"),
        max_daily_loss=Decimal("500"),
    )

    allocator = Allocator(config)

    strategy_intents = {
        "strategy_a": [
            PositionIntent(symbol="SPY", target_quantity=10, conviction=0.8, reason="test"),
            PositionIntent(symbol="MISSING", target_quantity=5, conviction=0.6, reason="test"),
        ],
    }

    current_prices = {
        "SPY": Decimal("450.00"),
        # MISSING has no price
    }

    result = allocator.allocate(strategy_intents, current_prices)

    # SPY should be included
    assert "SPY" in result.target_positions
    # MISSING should be skipped
    assert "MISSING" not in result.target_positions
    # Should have warning
    assert any("No price available" in w for w in result.warnings)


def test_allocator_aggregates_across_strategies():
    """Test that allocator aggregates target quantities for same symbol."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("5000"),
        max_daily_loss=Decimal("500"),
    )

    allocator = Allocator(config)

    # Both strategies want SPY
    strategy_intents = {
        "strategy_a": [
            PositionIntent(symbol="SPY", target_quantity=5, conviction=0.8, reason="test"),
        ],
        "strategy_b": [
            PositionIntent(symbol="SPY", target_quantity=3, conviction=0.6, reason="test"),
        ],
    }

    current_prices = {
        "SPY": Decimal("450.00"),
    }

    result = allocator.allocate(strategy_intents, current_prices)

    # Should aggregate: 5 + 3 = 8
    assert result.target_positions["SPY"] == 8


def test_allocator_no_strategies():
    """Test allocator behavior with no strategies."""
    config = Config(
        max_positions_notional=Decimal("10000"),
        max_order_notional=Decimal("1000"),
        max_daily_loss=Decimal("500"),
    )

    allocator = Allocator(config)

    result = allocator.allocate({}, {})

    assert result.target_positions == {}
    assert result.strategy_budgets == {}
    assert len(result.warnings) > 0
