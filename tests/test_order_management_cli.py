"""Tests for order management CLI commands."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.app.__main__ import run_cancel_order, run_list_open_orders, run_replace_order
from src.app.config import Config


@pytest.fixture
def mock_config():
    """Create mock config for testing."""
    return Config(
        mode="mock",
        alpaca_base_url="https://paper-api.alpaca.markets",
        max_order_notional=10000,
        max_positions_notional=50000,
    )


@pytest.fixture
def paper_config():
    """Create paper mode config."""
    return Config(
        mode="paper",
        alpaca_base_url="https://paper-api.alpaca.markets",
        max_order_notional=10000,
        max_positions_notional=50000,
    )


@pytest.fixture
def live_config():
    """Create live mode config."""
    return Config(
        mode="live",
        alpaca_base_url="https://api.alpaca.markets",
        max_order_notional=10000,
        max_positions_notional=50000,
    )


class TestListOpenOrders:
    """Tests for run_list_open_orders."""

    def test_mock_mode_succeeds_without_safety_gates(self, mock_config, capsys):
        """Test that mock mode works without live trading safety gates."""
        mock_config.mode = "mock"

        exit_code = run_list_open_orders(mock_config, i_understand_live_trading=False)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "MOCK MODE" in captured.out
        assert "MockBroker" in captured.out
        assert "No open orders found" in captured.out

    def test_paper_mode_succeeds_without_safety_gates(self, paper_config, monkeypatch, capsys):
        """Test that paper mode works without live trading safety gates."""
        # Mock API keys
        monkeypatch.setenv("ALPACA_API_KEY", "test-key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")

        # Mock AlpacaBroker
        with patch("src.app.__main__.AlpacaBroker") as mock_broker_cls:
            mock_broker = MagicMock()
            mock_broker.list_open_orders_detailed.return_value = []
            mock_broker_cls.return_value = mock_broker

            exit_code = run_list_open_orders(paper_config, i_understand_live_trading=False)

            assert exit_code == 0
            captured = capsys.readouterr()
            assert "PAPER MODE" in captured.out
            assert "Connected to Alpaca (PAPER mode)" in captured.out

    def test_live_mode_requires_safety_gates(self, live_config, monkeypatch, capsys):
        """Test that live mode requires safety gates."""
        monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")

        exit_code = run_list_open_orders(live_config, i_understand_live_trading=False)

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "LIVE MODE" in captured.out
        assert "--i-understand-live-trading" in captured.err

    def test_live_mode_succeeds_with_all_safety_gates(self, live_config, monkeypatch, capsys):
        """Test that live mode succeeds with all safety gates."""
        monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
        monkeypatch.setenv("ALPACA_API_KEY", "test-key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")

        with patch("src.app.__main__.AlpacaBroker") as mock_broker_cls:
            mock_broker = MagicMock()
            mock_broker.list_open_orders_detailed.return_value = []
            mock_broker_cls.return_value = mock_broker

            exit_code = run_list_open_orders(live_config, i_understand_live_trading=True)

            assert exit_code == 0
            captured = capsys.readouterr()
            assert "LIVE MODE" in captured.out

    def test_paper_mode_without_credentials_fails(self, paper_config, monkeypatch, capsys):
        """Test that paper mode fails without API credentials."""
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

        exit_code = run_list_open_orders(paper_config, i_understand_live_trading=False)

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "API credentials" in captured.err

    def test_list_orders_displays_table(self, mock_config, capsys):
        """Test that list orders displays clean table output."""
        mock_config.mode = "mock"

        with patch("src.app.__main__.MockBroker") as mock_broker_cls:
            mock_broker = MagicMock()
            # Create MagicMock order instead of OrderRecord
            mock_order = MagicMock()
            mock_order.id = "test-broker-id"
            mock_order.symbol = "AAPL"
            mock_order.side = MagicMock()
            mock_order.side.value = "buy"
            mock_order.quantity = 10
            mock_order.type = MagicMock()
            mock_order.type.value = "limit"
            mock_order.status = MagicMock()
            mock_order.status.value = "new"
            mock_order.price = Decimal("150.00")
            mock_order.client_order_id = "test-client-id"
            mock_broker.list_open_orders_detailed.return_value = [mock_order]
            mock_broker_cls.return_value = mock_broker

            exit_code = run_list_open_orders(mock_config, i_understand_live_trading=False)

            assert exit_code == 0
            captured = capsys.readouterr()
            assert "AAPL" in captured.out
            assert "buy" in captured.out
            assert "10" in captured.out


class TestCancelOrder:
    """Tests for run_cancel_order."""

    def test_mock_mode_succeeds_without_safety_gates(self, mock_config, capsys):
        """Test that mock mode cancel works without live trading safety gates."""
        mock_config.mode = "mock"

        with patch("src.app.__main__.MockBroker") as mock_broker_cls:
            mock_broker = MagicMock()
            mock_broker.cancel_order.return_value = True
            mock_broker_cls.return_value = mock_broker

            exit_code = run_cancel_order(
                mock_config,
                i_understand_live_trading=False,
                order_id="test-order-id",
                client_order_id=None,
            )

            assert exit_code == 0
            captured = capsys.readouterr()
            assert "MOCK MODE" in captured.out
            assert "MockBroker" in captured.out
            assert "CANCELED SUCCESSFULLY" in captured.out

    def test_paper_mode_succeeds_without_safety_gates(self, paper_config, monkeypatch, capsys):
        """Test that paper mode cancel works without live trading safety gates."""
        monkeypatch.setenv("ALPACA_API_KEY", "test-key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")

        with patch("src.app.__main__.AlpacaBroker") as mock_broker_cls:
            mock_broker = MagicMock()
            mock_broker.cancel_order.return_value = True
            mock_broker_cls.return_value = mock_broker

            exit_code = run_cancel_order(
                paper_config,
                i_understand_live_trading=False,
                order_id="test-order-id",
                client_order_id=None,
            )

            assert exit_code == 0
            captured = capsys.readouterr()
            assert "PAPER MODE" in captured.out

    def test_live_mode_requires_safety_gates(self, live_config, monkeypatch, capsys):
        """Test that live mode cancel requires safety gates."""
        monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")

        exit_code = run_cancel_order(
            live_config,
            i_understand_live_trading=False,
            order_id="test-order-id",
            client_order_id=None,
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "LIVE MODE" in captured.out
        assert "--i-understand-live-trading" in captured.err

    def test_no_order_id_fails(self, mock_config, capsys):
        """Test that missing order ID fails."""
        mock_config.mode = "mock"

        exit_code = run_cancel_order(
            mock_config,
            i_understand_live_trading=False,
            order_id=None,
            client_order_id=None,
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "No order ID provided" in captured.err

    def test_cancel_by_client_order_id(self, mock_config, capsys):
        """Test cancel by client order ID."""
        mock_config.mode = "mock"

        with patch("src.app.__main__.MockBroker") as mock_broker_cls:
            mock_broker = MagicMock()
            mock_broker.cancel_order_by_client_id.return_value = True
            mock_broker_cls.return_value = mock_broker

            exit_code = run_cancel_order(
                mock_config,
                i_understand_live_trading=False,
                order_id=None,
                client_order_id="test-client-id",
            )

            assert exit_code == 0
            mock_broker.cancel_order_by_client_id.assert_called_once_with("test-client-id")

    def test_cancel_failure_returns_error_code(self, mock_config, capsys):
        """Test that cancel failure returns exit code 2."""
        mock_config.mode = "mock"

        with patch("src.app.__main__.MockBroker") as mock_broker_cls:
            mock_broker = MagicMock()
            mock_broker.cancel_order.return_value = False
            mock_broker_cls.return_value = mock_broker

            exit_code = run_cancel_order(
                mock_config,
                i_understand_live_trading=False,
                order_id="test-order-id",
                client_order_id=None,
            )

            assert exit_code == 2
            captured = capsys.readouterr()
            assert "Failed to cancel order" in captured.err


class TestReplaceOrder:
    """Tests for run_replace_order."""

    def test_mock_mode_succeeds_without_safety_gates(self, mock_config, capsys):
        """Test that mock mode replace works without live trading safety gates."""
        mock_config.mode = "mock"

        with patch("src.app.__main__.MockBroker") as mock_broker_cls:
            mock_broker = MagicMock()

            # Mock existing order
            existing_order = MagicMock()
            existing_order.symbol = "AAPL"
            existing_order.side = MagicMock()
            existing_order.side.value = "buy"
            existing_order.quantity = 10
            existing_order.price = Decimal("150.00")
            mock_broker.get_order_status.return_value = existing_order

            # Mock new order
            new_order = MagicMock()
            new_order.id = "new-order-id"
            new_order.status = MagicMock()
            new_order.status.value = "new"
            new_order.symbol = "AAPL"
            new_order.side = MagicMock()
            new_order.side.value = "buy"
            new_order.quantity = 10
            new_order.price = Decimal("155.00")
            mock_broker.replace_order.return_value = new_order

            mock_broker_cls.return_value = mock_broker

            exit_code = run_replace_order(
                mock_config,
                i_understand_live_trading=False,
                order_id="test-order-id",
                limit_price=155.00,
                quantity=None,
            )

            assert exit_code == 0
            captured = capsys.readouterr()
            assert "MOCK MODE" in captured.out
            assert "REPLACED SUCCESSFULLY" in captured.out

    def test_paper_mode_succeeds_without_safety_gates(self, paper_config, monkeypatch, capsys):
        """Test that paper mode replace works without live trading safety gates."""
        monkeypatch.setenv("ALPACA_API_KEY", "test-key")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")

        with patch("src.app.__main__.AlpacaBroker") as mock_broker_cls:
            mock_broker = MagicMock()

            # Mock existing order
            existing_order = MagicMock()
            existing_order.symbol = "AAPL"
            existing_order.side = MagicMock()
            existing_order.side.value = "buy"
            existing_order.quantity = 10
            existing_order.price = Decimal("150.00")
            mock_broker.get_order_status.return_value = existing_order

            # Mock new order
            new_order = MagicMock()
            new_order.id = "new-order-id"
            new_order.status = MagicMock()
            new_order.status.value = "new"
            new_order.symbol = "AAPL"
            new_order.side = MagicMock()
            new_order.side.value = "buy"
            new_order.quantity = 10
            new_order.price = Decimal("155.00")
            mock_broker.replace_order.return_value = new_order

            mock_broker_cls.return_value = mock_broker

            exit_code = run_replace_order(
                paper_config,
                i_understand_live_trading=False,
                order_id="test-order-id",
                limit_price=155.00,
                quantity=None,
            )

            assert exit_code == 0
            captured = capsys.readouterr()
            assert "PAPER MODE" in captured.out

    def test_live_mode_requires_safety_gates(self, live_config, monkeypatch, capsys):
        """Test that live mode replace requires safety gates."""
        monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")

        exit_code = run_replace_order(
            live_config,
            i_understand_live_trading=False,
            order_id="test-order-id",
            limit_price=155.00,
            quantity=None,
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "LIVE MODE" in captured.out
        assert "--i-understand-live-trading" in captured.err

    def test_replace_validates_through_risk_manager(self, mock_config, capsys):
        """Test that replace validates through RiskManager."""
        mock_config.mode = "mock"

        with patch("src.app.__main__.MockBroker") as mock_broker_cls:
            mock_broker = MagicMock()

            # Mock existing order
            existing_order = MagicMock()
            existing_order.symbol = "AAPL"
            existing_order.side = MagicMock()
            existing_order.side.value = "buy"
            existing_order.quantity = 10
            existing_order.price = Decimal("150.00")
            mock_broker.get_order_status.return_value = existing_order
            mock_broker_cls.return_value = mock_broker

            # Don't mock RiskManager - use actual implementation with config limits
            # Set a very low limit to trigger failure
            mock_config.max_order_notional = 1  # $1 max - will fail for 10 shares @ $155

            exit_code = run_replace_order(
                mock_config,
                i_understand_live_trading=False,
                order_id="test-order-id",
                limit_price=155.00,
                quantity=None,
            )

            assert exit_code == 1
            captured = capsys.readouterr()
            assert "failed risk check" in captured.err

    def test_replace_failure_returns_error_code(self, mock_config, capsys):
        """Test that replace failure returns exit code 2."""
        mock_config.mode = "mock"

        with patch("src.app.__main__.MockBroker") as mock_broker_cls:
            mock_broker = MagicMock()

            # Mock existing order
            existing_order = MagicMock()
            existing_order.symbol = "AAPL"
            existing_order.side = MagicMock()
            existing_order.side.value = "buy"
            existing_order.quantity = 10
            existing_order.price = Decimal("150.00")
            mock_broker.get_order_status.return_value = existing_order

            # Mock replace failure
            mock_broker.replace_order.side_effect = Exception("Broker error")
            mock_broker_cls.return_value = mock_broker

            exit_code = run_replace_order(
                mock_config,
                i_understand_live_trading=False,
                order_id="test-order-id",
                limit_price=155.00,
                quantity=None,
            )

            assert exit_code == 2
            captured = capsys.readouterr()
            assert "Failed to replace order" in captured.err


class TestExitCodes:
    """Tests for consistent exit code behavior."""

    def test_list_success_returns_zero(self, mock_config):
        """Test that successful list returns 0."""
        mock_config.mode = "mock"
        exit_code = run_list_open_orders(mock_config, i_understand_live_trading=False)
        assert exit_code == 0

    def test_list_user_error_returns_one(self, live_config, monkeypatch):
        """Test that user error returns 1."""
        monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")
        exit_code = run_list_open_orders(live_config, i_understand_live_trading=False)
        assert exit_code == 1

    def test_cancel_success_returns_zero(self, mock_config):
        """Test that successful cancel returns 0."""
        mock_config.mode = "mock"

        with patch("src.app.__main__.MockBroker") as mock_broker_cls:
            mock_broker = MagicMock()
            mock_broker.cancel_order.return_value = True
            mock_broker_cls.return_value = mock_broker

            exit_code = run_cancel_order(
                mock_config, i_understand_live_trading=False, order_id="test-id", client_order_id=None
            )
            assert exit_code == 0

    def test_cancel_user_error_returns_one(self, mock_config):
        """Test that user error returns 1."""
        mock_config.mode = "mock"
        exit_code = run_cancel_order(
            mock_config, i_understand_live_trading=False, order_id=None, client_order_id=None
        )
        assert exit_code == 1
