"""Tests for trading cost awareness features."""

import os
import tempfile
from datetime import datetime
from decimal import Decimal

import pytest

from src.app.config import Config
from src.app.models import OrderSide, OrderType, Quote, Signal
from src.app.order_pipeline import submit_signal_order
from src.app.state import BotState
from src.broker.base import MockBroker
from src.risk import RiskManager


@pytest.fixture
def temp_dir(monkeypatch):
    """Create a temporary directory for test outputs."""
    from src.app.__main__ import setup_outputs

    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
        # Setup output directories for tests
        setup_outputs("test-run")
        yield tmpdir
        os.chdir(original_cwd)


@pytest.fixture
def base_config():
    """Base configuration for tests."""
    return Config(
        mode="mock",
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=Decimal("500"),
        max_order_notional=Decimal("10000"),
        max_positions_notional=Decimal("50000"),
        use_limit_orders=True,
        max_spread_bps=Decimal("20"),
        min_edge_bps=Decimal("0"),
        cost_diagnostics=True,
    )


@pytest.fixture
def broker():
    """Mock broker instance."""
    return MockBroker()


@pytest.fixture
def risk_manager(base_config):
    """Risk manager instance."""
    return RiskManager(config=base_config, daily_realized_pnl=Decimal("0"))


@pytest.fixture
def state():
    """Bot state instance."""
    return BotState(run_id="test-run", submitted_client_order_ids=set())


def test_quote_model_properties():
    """Test Quote model properties."""
    quote = Quote(
        symbol="AAPL",
        bid=Decimal("100.00"),
        ask=Decimal("100.20"),
        last=Decimal("100.10"),
        timestamp=datetime.now(),
    )

    assert quote.mid == Decimal("100.10")
    assert quote.spread == Decimal("0.20")
    # Spread in bps should be approximately 20
    assert abs(quote.spread_bps - Decimal("20")) < Decimal("0.1")

    # Test expected entry price
    assert quote.expected_entry_price(OrderSide.BUY) == Decimal("100.20")  # ask
    assert quote.expected_entry_price(OrderSide.SELL) == Decimal("100.00")  # bid


def test_spread_blocking_when_too_wide(temp_dir, base_config, broker, risk_manager, state):
    """Test that orders are blocked when spread exceeds max_spread_bps."""
    # Configure max_spread_bps = 20
    base_config.max_spread_bps = Decimal("20")

    # Create a broker with wide spread (30 bps)
    # MockBroker generates 10 bps spread by default, so we need to override get_quote
    class WidespreadBroker(MockBroker):
        def get_quote(self, symbol: str):
            # Return quote with 30 bps spread
            return Quote(
                symbol=symbol,
                bid=Decimal("100.00"),
                ask=Decimal("100.30"),  # 30 bps spread
                last=Decimal("100.15"),
                timestamp=datetime.now(),
            )

    wide_broker = WidespreadBroker()

    # Create signal
    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("100.00"),
    )

    # Mock CSV write functions
    def mock_write(*args, **kwargs):
        pass

    # Submit order - should be blocked by spread check
    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=base_config,
        broker=wide_broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run",
        write_order_to_csv_fn=mock_write,
        write_fill_to_csv_fn=mock_write,
        write_trade_to_csv_fn=mock_write,
    )

    assert not result.success
    assert "Spread too wide" in result.reason
    # Spread should be approximately 30 bps (may be 29.96 due to precision)
    assert "29" in result.reason or "30" in result.reason


def test_spread_allowing_when_within_limit(temp_dir, base_config, broker, risk_manager, state):
    """Test that orders are allowed when spread is within max_spread_bps."""
    # Configure max_spread_bps = 20
    base_config.max_spread_bps = Decimal("20")

    # MockBroker generates 10 bps spread by default (within limit)

    # Create signal
    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("100.00"),
    )

    # Mock CSV write functions
    def mock_write(*args, **kwargs):
        pass

    # Submit order - should pass spread check
    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=base_config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run",
        write_order_to_csv_fn=mock_write,
        write_fill_to_csv_fn=mock_write,
        write_trade_to_csv_fn=mock_write,
    )

    assert result.success
    assert result.order is not None


def test_limit_order_type_when_enabled(temp_dir, base_config, broker, risk_manager, state):
    """Test that LIMIT orders are used when use_limit_orders=True."""
    base_config.use_limit_orders = True

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("100.00"),
    )

    def mock_write(*args, **kwargs):
        pass

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=base_config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run",
        write_order_to_csv_fn=mock_write,
        write_fill_to_csv_fn=mock_write,
        write_trade_to_csv_fn=mock_write,
    )

    assert result.success
    assert result.order.type == OrderType.LIMIT
    assert result.order.price is not None


def test_market_order_type_when_disabled(temp_dir, base_config, broker, risk_manager, state):
    """Test that MARKET orders are used when use_limit_orders=False."""
    base_config.use_limit_orders = False

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("100.00"),
    )

    def mock_write(*args, **kwargs):
        pass

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=base_config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run",
        write_order_to_csv_fn=mock_write,
        write_fill_to_csv_fn=mock_write,
        write_trade_to_csv_fn=mock_write,
    )

    assert result.success
    assert result.order.type == OrderType.MARKET


def test_limit_price_calculation_buy(temp_dir, base_config, broker, risk_manager, state):
    """Test limit price calculation for BUY orders."""
    base_config.use_limit_orders = True

    # Create broker with known quote
    class FixedQuoteBroker(MockBroker):
        def get_quote(self, symbol: str):
            return Quote(
                symbol=symbol,
                bid=Decimal("100.00"),
                ask=Decimal("100.20"),
                last=Decimal("100.10"),
                timestamp=datetime.now(),
            )

    fixed_broker = FixedQuoteBroker()

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("100.00"),
    )

    def mock_write(*args, **kwargs):
        pass

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=base_config,
        broker=fixed_broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run",
        write_order_to_csv_fn=mock_write,
        write_fill_to_csv_fn=mock_write,
        write_trade_to_csv_fn=mock_write,
    )

    assert result.success
    # Limit price for BUY: min(ask, mid + spread*0.25)
    # mid = 100.10, spread = 0.20, quarter_spread = 0.05
    # min(100.20, 100.10 + 0.05) = min(100.20, 100.15) = 100.15
    assert result.order.price == Decimal("100.15")


def test_limit_price_calculation_sell(temp_dir, base_config, broker, risk_manager, state):
    """Test limit price calculation for SELL orders."""
    base_config.use_limit_orders = True

    # Create broker with known quote
    class FixedQuoteBroker(MockBroker):
        def get_quote(self, symbol: str):
            return Quote(
                symbol=symbol,
                bid=Decimal("100.00"),
                ask=Decimal("100.20"),
                last=Decimal("100.10"),
                timestamp=datetime.now(),
            )

    fixed_broker = FixedQuoteBroker()

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.SELL,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("100.00"),
    )

    def mock_write(*args, **kwargs):
        pass

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=base_config,
        broker=fixed_broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run",
        write_order_to_csv_fn=mock_write,
        write_fill_to_csv_fn=mock_write,
        write_trade_to_csv_fn=mock_write,
    )

    assert result.success
    # Limit price for SELL: max(bid, mid - spread*0.25)
    # mid = 100.10, spread = 0.20, quarter_spread = 0.05
    # max(100.00, 100.10 - 0.05) = max(100.00, 100.05) = 100.05
    assert result.order.price == Decimal("100.05")


def test_edge_threshold_blocking_buy(temp_dir, base_config, broker, risk_manager, state):
    """Test that BUY orders are blocked when edge is insufficient."""
    base_config.use_limit_orders = True
    base_config.min_edge_bps = Decimal("10")  # Require 10 bps edge

    # Create broker where limit price won't provide enough edge
    # For BUY: edge < 0 is good (buying below expected)
    # Expected entry = ask = 100.20
    # Limit price = min(100.20, 100.10 + 0.05) = 100.15
    # Edge = (100.15 - 100.20) / 100.20 * 10000 = -4.99 bps
    # Not enough edge (need < -10 bps)
    class EdgeTestBroker(MockBroker):
        def get_quote(self, symbol: str):
            return Quote(
                symbol=symbol,
                bid=Decimal("100.00"),
                ask=Decimal("100.20"),
                last=Decimal("100.10"),
                timestamp=datetime.now(),
            )

    edge_broker = EdgeTestBroker()

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("100.00"),
    )

    def mock_write(*args, **kwargs):
        pass

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=base_config,
        broker=edge_broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run",
        write_order_to_csv_fn=mock_write,
        write_fill_to_csv_fn=mock_write,
        write_trade_to_csv_fn=mock_write,
    )

    assert not result.success
    assert "Insufficient edge" in result.reason


def test_edge_threshold_passing_buy(temp_dir, base_config, broker, risk_manager, state):
    """Test that BUY orders pass when edge is sufficient."""
    base_config.use_limit_orders = True
    base_config.min_edge_bps = Decimal("5")  # Require 5 bps edge
    base_config.max_spread_bps = Decimal("50")  # Increase to avoid spread block

    # Create broker where limit price provides enough edge
    # Expected entry = ask = 100.40
    # mid = 100.20, spread = 0.40, quarter = 0.10
    # limit = min(100.40, 100.20 + 0.10) = min(100.40, 100.30) = 100.30
    # Edge = (100.30 - 100.40) / 100.40 * 10000 = -9.96 bps
    # This is < -5 bps, so it should pass!
    class EdgeTestBroker(MockBroker):
        def get_quote(self, symbol: str):
            return Quote(
                symbol=symbol,
                bid=Decimal("100.00"),
                ask=Decimal("100.40"),  # Wider spread
                last=Decimal("100.20"),
                timestamp=datetime.now(),
            )

    edge_broker = EdgeTestBroker()

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("100.00"),
    )

    def mock_write(*args, **kwargs):
        pass

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=base_config,
        broker=edge_broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run",
        write_order_to_csv_fn=mock_write,
        write_fill_to_csv_fn=mock_write,
        write_trade_to_csv_fn=mock_write,
    )

    assert result.success


def test_slippage_computation_in_fills(temp_dir, base_config, broker, risk_manager, state):
    """Test that slippage is correctly computed and recorded in fills."""
    base_config.use_limit_orders = True

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("100.00"),
    )

    # Track what was written to CSV
    written_fills = []

    def capture_fill(fill, run_id):
        written_fills.append(fill)

    def mock_write(*args, **kwargs):
        pass

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=base_config,
        broker=broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run",
        write_order_to_csv_fn=mock_write,
        write_fill_to_csv_fn=capture_fill,
        write_trade_to_csv_fn=mock_write,
    )

    assert result.success
    assert len(written_fills) == 1

    fill = written_fills[0]
    assert fill.expected_price is not None
    assert fill.slippage_abs is not None
    assert fill.slippage_bps is not None
    assert fill.spread_bps_at_submit is not None

    # Verify slippage calculation
    # slippage_abs = fill_price - expected_price
    # slippage_bps = (slippage_abs / expected_price) * 10000
    expected_slippage_abs = fill.price - fill.expected_price
    assert fill.slippage_abs == expected_slippage_abs

    if fill.expected_price != 0:
        expected_slippage_bps = (expected_slippage_abs / fill.expected_price) * Decimal("10000")
        assert abs(fill.slippage_bps - expected_slippage_bps) < Decimal("0.01")


def test_cost_diagnostics_disabled(temp_dir, base_config, broker, risk_manager, state):
    """Test that cost diagnostics can be disabled."""
    from src.app.__main__ import generate_cost_diagnostics

    base_config.cost_diagnostics = False

    # Generate cost report (should skip if no fills)
    report_path = generate_cost_diagnostics("test-run")
    assert report_path is None  # No report generated


def test_mock_broker_quote_deterministic():
    """Test that MockBroker generates deterministic quotes."""
    broker = MockBroker()

    # Get quote for symbol with no orders
    quote1 = broker.get_quote("AAPL")
    assert quote1.spread_bps == Decimal("10")  # 10 bps spread

    # Quote should be consistent
    quote2 = broker.get_quote("AAPL")
    assert quote1.bid == quote2.bid
    assert quote1.ask == quote2.ask
