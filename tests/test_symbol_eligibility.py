"""Tests for symbol eligibility and liquidity guardrails."""

import os
import tempfile
from datetime import datetime
from decimal import Decimal

import pytest

from src.app.config import Config
from src.app.models import OrderSide, Quote, Signal
from src.app.order_pipeline import submit_signal_order
from src.app.state import BotState
from src.broker.base import MockBroker
from src.data.provider import MockDataProvider
from src.risk import RiskManager


@pytest.fixture
def temp_dir(monkeypatch):
    """Create a temporary directory for test outputs."""
    from src.app.__main__ import setup_outputs

    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
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
        use_limit_orders=False,  # Use market orders for simpler tests
        max_spread_bps=Decimal("1000"),  # Very high to not interfere
        min_edge_bps=Decimal("0"),
        cost_diagnostics=False,
        min_avg_volume=1_000_000,
        min_price=Decimal("2.00"),
        max_price=Decimal("1000.00"),
        require_quote=True,
        symbol_whitelist=[],
        symbol_blacklist=[],
        # Allow test symbols in risk manager
        allowed_symbols=[
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "TSLA",
            "PENNY",
            "EXPENSIVE",
            "ILLIQUID",
            "ANYSYMBOL",
        ],
    )


@pytest.fixture
def data_provider():
    """Mock data provider instance."""
    return MockDataProvider()


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


def test_whitelist_allows_listed_symbol(
    temp_dir, base_config, data_provider, broker, risk_manager, state
):
    """Test that whitelist allows only listed symbols."""
    base_config.symbol_whitelist = ["AAPL", "MSFT"]

    # AAPL should be allowed
    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("180.00"),
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
        data_provider=data_provider,
    )

    assert result.success


def test_whitelist_blocks_unlisted_symbol(
    temp_dir, base_config, data_provider, broker, risk_manager, state
):
    """Test that whitelist blocks symbols not in the list."""
    base_config.symbol_whitelist = ["AAPL", "MSFT"]

    # TSLA should be blocked
    signal = Signal(
        symbol="TSLA",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("250.00"),
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
        data_provider=data_provider,
    )

    assert not result.success
    assert "not in whitelist" in result.reason


def test_blacklist_blocks_symbol(temp_dir, base_config, data_provider, broker, risk_manager, state):
    """Test that blacklist blocks specified symbols."""
    base_config.symbol_blacklist = ["TSLA"]

    signal = Signal(
        symbol="TSLA",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("250.00"),
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
        data_provider=data_provider,
    )

    assert not result.success
    assert "in blacklist" in result.reason


def test_blacklist_wins_over_whitelist(
    temp_dir, base_config, data_provider, broker, risk_manager, state
):
    """Test that blacklist takes precedence over whitelist."""
    base_config.symbol_whitelist = ["AAPL", "TSLA"]
    base_config.symbol_blacklist = ["TSLA"]

    signal = Signal(
        symbol="TSLA",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("250.00"),
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
        data_provider=data_provider,
    )

    assert not result.success
    assert "in blacklist" in result.reason


def test_require_quote_blocks_when_missing(
    temp_dir, base_config, data_provider, broker, risk_manager, state
):
    """Test that require_quote blocks when quote is invalid."""
    base_config.require_quote = True

    # Create a broker with invalid quote
    class InvalidQuoteBroker(MockBroker):
        def get_quote(self, symbol: str):
            return Quote(
                symbol=symbol,
                bid=Decimal("0"),  # Invalid bid
                ask=Decimal("0"),  # Invalid ask
                last=Decimal("0"),
                timestamp=datetime.now(),
            )

    invalid_broker = InvalidQuoteBroker()

    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("180.00"),
    )

    def mock_write(*args, **kwargs):
        pass

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=base_config,
        broker=invalid_broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run",
        write_order_to_csv_fn=mock_write,
        write_fill_to_csv_fn=mock_write,
        write_trade_to_csv_fn=mock_write,
        data_provider=data_provider,
    )

    assert not result.success
    assert "quote missing" in result.reason


def test_min_price_blocks_low_priced_symbol(
    temp_dir, base_config, data_provider, broker, risk_manager, state
):
    """Test that min_price blocks low-priced symbols."""
    base_config.min_price = Decimal("2.00")

    # Create a broker with low price
    class LowPriceBroker(MockBroker):
        def get_quote(self, symbol: str):
            return Quote(
                symbol=symbol,
                bid=Decimal("0.80"),
                ask=Decimal("0.90"),
                last=Decimal("0.85"),
                timestamp=datetime.now(),
            )

    low_price_broker = LowPriceBroker()

    signal = Signal(
        symbol="PENNY",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("0.85"),
    )

    def mock_write(*args, **kwargs):
        pass

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=base_config,
        broker=low_price_broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run",
        write_order_to_csv_fn=mock_write,
        write_fill_to_csv_fn=mock_write,
        write_trade_to_csv_fn=mock_write,
        data_provider=data_provider,
    )

    assert not result.success
    assert "price=" in result.reason
    assert "< min_price" in result.reason


def test_max_price_blocks_high_priced_symbol(
    temp_dir, base_config, data_provider, broker, risk_manager, state
):
    """Test that max_price blocks high-priced symbols."""
    base_config.max_price = Decimal("1000.00")
    base_config.max_order_notional = Decimal("50000.00")  # High enough to not interfere

    # Create a broker with high price
    class HighPriceBroker(MockBroker):
        def get_quote(self, symbol: str):
            return Quote(
                symbol=symbol,
                bid=Decimal("1500.00"),
                ask=Decimal("1510.00"),
                last=Decimal("1505.00"),
                timestamp=datetime.now(),
            )

    high_price_broker = HighPriceBroker()

    signal = Signal(
        symbol="EXPENSIVE",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("1505.00"),
    )

    def mock_write(*args, **kwargs):
        pass

    result = submit_signal_order(
        signal=signal,
        quantity=10,
        config=base_config,
        broker=high_price_broker,
        risk_manager=risk_manager,
        state=state,
        run_id="test-run",
        write_order_to_csv_fn=mock_write,
        write_fill_to_csv_fn=mock_write,
        write_trade_to_csv_fn=mock_write,
        data_provider=data_provider,
    )

    assert not result.success
    assert "price=" in result.reason
    assert "> max_price" in result.reason


def test_avg_volume_blocks_low_volume_symbol(
    temp_dir, base_config, data_provider, broker, risk_manager, state
):
    """Test that min_avg_volume blocks low-volume symbols."""
    base_config.min_avg_volume = 1_000_000

    # Create a data provider with low volume
    class LowVolumeDataProvider(MockDataProvider):
        def get_avg_volume(self, symbol: str, lookback_days: int = 20) -> int:
            return 500_000  # Below threshold

    low_volume_provider = LowVolumeDataProvider()

    signal = Signal(
        symbol="ILLIQUID",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("50.00"),
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
        data_provider=low_volume_provider,
    )

    assert not result.success
    assert "avg_volume=" in result.reason
    assert "< min_avg_volume" in result.reason


def test_happy_path_allows_eligible_symbol(
    temp_dir, base_config, data_provider, broker, risk_manager, state
):
    """Test that eligible symbols pass all checks."""
    # All defaults should allow AAPL
    signal = Signal(
        symbol="AAPL",
        side=OrderSide.BUY,
        timestamp=datetime.now(),
        reason="Test signal",
        price=Decimal("180.00"),
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
        data_provider=data_provider,
    )

    assert result.success


def test_empty_whitelist_allows_all_symbols(
    temp_dir, base_config, data_provider, broker, risk_manager, state
):
    """Test that empty whitelist allows all symbols."""
    base_config.symbol_whitelist = []  # Empty = allow all

    signal = Signal(
        symbol="ANYSYMBOL",
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
        data_provider=data_provider,
    )

    assert result.success
