"""Tests for CLI interface."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

from src.app.__main__ import main, parse_args


def test_parse_args_default_mode():
    """Test that default mode is dry-run."""
    args = parse_args([])
    assert args.mode == "dry-run"


def test_parse_args_with_mode():
    """Test parsing mode argument."""
    args = parse_args(["--mode", "paper"])
    assert args.mode == "paper"


def test_parse_args_with_symbols():
    """Test parsing symbols argument."""
    args = parse_args(["--symbols", "AAPL,MSFT,GOOGL"])
    assert args.symbols == "AAPL,MSFT,GOOGL"


def test_parse_args_with_max_iterations():
    """Test parsing max-iterations argument."""
    args = parse_args(["--max-iterations", "10"])
    assert args.max_iterations == 10


def test_parse_args_with_iterations_alias():
    """Test parsing --iterations as alias for --max-iterations."""
    args = parse_args(["--iterations", "10"])
    assert args.max_iterations == 10


def test_parse_args_with_run_id():
    """Test parsing run-id argument."""
    args = parse_args(["--run-id", "test-123"])
    assert args.run_id == "test-123"


def test_parse_args_live_trading_flag():
    """Test parsing i-understand-live-trading flag."""
    args = parse_args(["--i-understand-live-trading"])
    assert args.i_understand_live_trading is True


def test_parse_args_live_trading_flag_default_false():
    """Test that live trading flag defaults to False."""
    args = parse_args([])
    assert args.i_understand_live_trading is False


def test_main_default_dry_run(monkeypatch):
    """Test that default mode calls loop with dry-run."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main([])

    assert result == 0
    mock_loop.assert_called_once()
    call_kwargs = mock_loop.call_args.kwargs
    assert call_kwargs["mode"] == "dry-run"
    assert call_kwargs["run_id"] is None
    assert call_kwargs["symbols"] is None
    assert call_kwargs["max_iterations"] is None


def test_main_live_without_ack_fails(monkeypatch, capsys):
    """Test that live mode without acknowledgment returns non-zero and doesn't call loop."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main(["--mode", "live"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "live trading" in captured.err.lower()
    assert "i-understand-live-trading" in captured.err.lower()


def test_main_live_with_ack_succeeds(monkeypatch):
    """Test that live mode with acknowledgment calls loop and returns 0."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys for live mode
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")

    result = main(["--mode", "live", "--i-understand-live-trading"])

    assert result == 0
    mock_loop.assert_called_once()
    call_kwargs = mock_loop.call_args.kwargs
    assert call_kwargs["mode"] == "live"


def test_main_paper_mode(monkeypatch):
    """Test that paper mode calls loop with correct mode."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys for paper mode
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")

    result = main(["--mode", "paper"])

    assert result == 0
    mock_loop.assert_called_once()
    call_kwargs = mock_loop.call_args.kwargs
    assert call_kwargs["mode"] == "paper"


def test_main_with_symbols(monkeypatch):
    """Test that symbols argument is passed to loop."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main(["--symbols", "AAPL,MSFT"])

    assert result == 0
    mock_loop.assert_called_once()
    call_kwargs = mock_loop.call_args.kwargs
    assert call_kwargs["symbols"] == ["AAPL", "MSFT"]


def test_main_with_symbols_whitespace(monkeypatch):
    """Test that symbols with whitespace are trimmed."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main(["--symbols", "AAPL, MSFT , GOOGL"])

    assert result == 0
    call_kwargs = mock_loop.call_args.kwargs
    assert call_kwargs["symbols"] == ["AAPL", "MSFT", "GOOGL"]


def test_main_with_max_iterations(monkeypatch):
    """Test that max-iterations argument is passed to loop."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main(["--max-iterations", "5"])

    assert result == 0
    mock_loop.assert_called_once()
    call_kwargs = mock_loop.call_args.kwargs
    assert call_kwargs["max_iterations"] == 5


def test_main_with_iterations_alias(monkeypatch):
    """Test that --iterations alias is passed to loop as max_iterations."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main(["--iterations", "5"])

    assert result == 0
    mock_loop.assert_called_once()
    call_kwargs = mock_loop.call_args.kwargs
    assert call_kwargs["max_iterations"] == 5


def test_main_with_custom_run_id(monkeypatch):
    """Test that custom run-id is passed to loop."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main(["--run-id", "test-run-123"])

    assert result == 0
    mock_loop.assert_called_once()
    call_kwargs = mock_loop.call_args.kwargs
    assert call_kwargs["run_id"] == "test-run-123"


def test_main_exception_handling(monkeypatch, capsys):
    """Test that exceptions from loop are caught and return non-zero."""
    mock_loop = MagicMock(side_effect=RuntimeError("Test error"))
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main([])

    assert result == 1
    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "Test error" in captured.err


def test_main_paper_mode_without_keys_fails(monkeypatch, capsys):
    """Test that paper mode without API keys returns non-zero and doesn't call loop."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Clear any existing API key environment variables
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    result = main(["--mode", "paper"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "paper mode requires alpaca api credentials" in captured.err.lower()
    assert "ALPACA_API_KEY" in captured.err
    assert "ALPACA_SECRET_KEY" in captured.err


def test_main_live_mode_with_ack_without_keys_fails(monkeypatch, capsys):
    """Test that live mode with ack but without API keys returns non-zero and doesn't call loop."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Clear any existing API key environment variables
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    result = main(["--mode", "live", "--i-understand-live-trading"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "live mode requires alpaca api credentials" in captured.err.lower()
    assert "ALPACA_API_KEY" in captured.err
    assert "ALPACA_SECRET_KEY" in captured.err


def test_parse_args_preflight_flag():
    """Test parsing preflight flag."""
    args = parse_args(["--preflight"])
    assert args.preflight is True


def test_parse_args_preflight_flag_default_false():
    """Test that preflight flag defaults to False."""
    args = parse_args([])
    assert args.preflight is False


def test_preflight_dry_run_mode(monkeypatch, capsys):
    """Test that preflight in dry-run returns 0 and does not call run_trading_loop."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main(["--preflight"])

    assert result == 0
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "dry-run mode" in captured.out.lower()
    assert "no alpaca connectivity" in captured.out.lower()
    assert "OK" in captured.out


def test_preflight_paper_mode_without_keys(monkeypatch, capsys):
    """Test that preflight in paper without keys returns 1 and does not call run_trading_loop."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Clear any existing API key environment variables
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    result = main(["--mode", "paper", "--preflight"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "paper mode requires alpaca api credentials" in captured.err.lower()


def test_preflight_paper_mode_with_keys_success(monkeypatch, capsys):
    """Test that preflight in paper with keys and mocked 200 response returns 0 and does not call run_trading_loop."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")

    # Mock urllib.request.urlopen to return a successful response
    mock_response = Mock()
    mock_response.status = 200
    mock_response.read.return_value = (
        b'{"id":"test-account","status":"ACTIVE","currency":"USD","buying_power":"100000.00"}'
    )
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = main(["--mode", "paper", "--preflight"])

    assert result == 0
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "Connection successful" in captured.out
    assert "test-account" in captured.out
    assert "ACTIVE" in captured.out
    assert "OK" in captured.out


def test_preflight_live_mode_without_acknowledgment(monkeypatch, capsys):
    """Test that preflight in live without acknowledgment returns 1."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")

    result = main(["--mode", "live", "--preflight"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "live trading mode requires explicit acknowledgment" in captured.err.lower()


def test_preflight_live_mode_with_acknowledgment_success(monkeypatch, capsys):
    """Test that preflight in live with ack and mocked 200 response returns 0 and does not call run_trading_loop."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")

    # Mock urllib.request.urlopen to return a successful response
    mock_response = Mock()
    mock_response.status = 200
    mock_response.read.return_value = (
        b'{"id":"live-account","status":"ACTIVE","currency":"USD","buying_power":"50000.00"}'
    )
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = main(["--mode", "live", "--i-understand-live-trading", "--preflight"])

    assert result == 0
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "Connection successful" in captured.out
    assert "live-account" in captured.out
    assert "OK" in captured.out


def test_preflight_paper_mode_http_error(monkeypatch, capsys):
    """Test that preflight handles HTTP errors properly."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys
    monkeypatch.setenv("ALPACA_API_KEY", "bad_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "bad_secret")

    # Mock urllib.request.urlopen to raise HTTPError
    from urllib.error import HTTPError

    mock_error = HTTPError(
        "https://paper-api.alpaca.markets/v2/account", 401, "Unauthorized", {}, None
    )
    mock_error.read = Mock(return_value=b'{"message":"Invalid credentials"}')

    with patch("urllib.request.urlopen", side_effect=mock_error):
        result = main(["--mode", "paper", "--preflight"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "401" in captured.err


def test_parse_args_paper_test_order():
    """Test parsing paper-test-order flag."""
    args = parse_args(["--paper-test-order", "AAPL", "10"])
    assert args.paper_test_order == ["AAPL", "10"]


def test_paper_test_order_success(monkeypatch, capsys):
    """Test that paper test order works correctly."""
    from datetime import datetime
    from decimal import Decimal

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")

    # Mock the AlpacaBroker
    from src.app.models import Order, OrderSide, OrderStatus, OrderType

    mock_order = Order(
        id="test-order-123",
        symbol="AAPL",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=1,
        status=OrderStatus.FILLED,
        submitted_at=datetime.now(),
        filled_price=Decimal("150.00"),
    )

    mock_broker = MagicMock()
    mock_broker.submit_order.return_value = mock_order

    with patch("src.app.__main__.AlpacaBroker", return_value=mock_broker):
        result = main(["--mode", "paper", "--paper-test-order", "AAPL", "1"])

    assert result == 0
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "Paper test order: AAPL x 1" in captured.out
    assert "Order submitted successfully" in captured.out
    assert "test-order-123" in captured.out


def test_paper_test_order_refuses_live_mode(monkeypatch, capsys):
    """Test that paper test order refuses to run in live mode."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")

    result = main(["--mode", "live", "--paper-test-order", "AAPL", "1"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "cannot be used with --mode live" in captured.err


def test_paper_test_order_invalid_quantity(monkeypatch, capsys):
    """Test that paper test order validates quantity."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main(["--paper-test-order", "AAPL", "invalid"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "Invalid quantity" in captured.err


def test_paper_test_order_without_keys(monkeypatch, capsys):
    """Test that paper test order requires API keys."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Clear API keys
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    result = main(["--paper-test-order", "AAPL", "1"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires Alpaca API credentials" in captured.err


def test_parse_args_once_flag():
    """Test parsing --once flag."""
    args = parse_args(["--once"])
    assert args.once is True


def test_parse_args_once_flag_default_false():
    """Test that --once defaults to False."""
    args = parse_args([])
    assert args.once is False


def test_parse_args_compute_after_hours_flag():
    """Test parsing --compute-after-hours flag."""
    args = parse_args(["--compute-after-hours"])
    assert args.compute_after_hours is True


def test_parse_args_allow_after_hours_orders_flag():
    """Test parsing --allow-after-hours-orders flag."""
    args = parse_args(["--allow-after-hours-orders"])
    assert args.allow_after_hours_orders is True


def test_once_flag_runs_one_iteration(monkeypatch):
    """Test that --once flag runs exactly 1 iteration."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main(["--once"])

    assert result == 0
    mock_loop.assert_called_once()
    call_kwargs = mock_loop.call_args.kwargs
    assert call_kwargs["max_iterations"] == 1


def test_allow_after_hours_orders_refuses_live_mode(monkeypatch, capsys):
    """Test that --allow-after-hours-orders refuses to work in live mode."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")

    result = main(
        [
            "--mode",
            "live",
            "--i-understand-live-trading",
            "--compute-after-hours",
            "--allow-after-hours-orders",
        ]
    )

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "cannot be used with --mode live" in captured.err


def test_allow_after_hours_orders_requires_compute_after_hours(monkeypatch, capsys):
    """Test that --allow-after-hours-orders requires --compute-after-hours."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main(["--allow-after-hours-orders"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires --compute-after-hours" in captured.err


def test_compute_after_hours_passed_to_loop(monkeypatch):
    """Test that --compute-after-hours flag is passed to trading loop."""
    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    result = main(["--compute-after-hours"])

    assert result == 0
    mock_loop.assert_called_once()
    call_kwargs = mock_loop.call_args.kwargs
    assert call_kwargs["compute_after_hours"] is True
    assert call_kwargs["allow_after_hours_orders"] is False


def test_parse_args_test_order_flag():
    """Test parsing --test-order flag."""
    args = parse_args(["--test-order"])
    assert args.test_order is True


def test_parse_args_test_order_flag_default_false():
    """Test that --test-order defaults to False."""
    args = parse_args([])
    assert args.test_order is False


def test_test_order_requires_live_mode(monkeypatch, capsys):
    """Test that --test-order requires --mode live."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Mock load_config to return a config (mode override will be applied by main)
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    result = main(["--mode", "paper", "--test-order"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires --mode live" in captured.err


def test_test_order_requires_i_understand_live_trading(monkeypatch, capsys):
    """Test that --test-order requires --i-understand-live-trading flag."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Mock load_config to return a config (mode override will be applied by main)
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    # Don't set --i-understand-live-trading
    result = main(["--mode", "live", "--test-order"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires --i-understand-live-trading" in captured.err


def test_test_order_requires_enable_live_trading_env(monkeypatch, capsys):
    """Test that --test-order requires ENABLE_LIVE_TRADING=true env var."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")

    # Don't set ENABLE_LIVE_TRADING or set it to false
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)

    # Mock load_config to return a config (mode override will be applied by main)
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    result = main(["--mode", "live", "--i-understand-live-trading", "--test-order"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires ENABLE_LIVE_TRADING=true" in captured.err


def test_test_order_requires_api_keys(monkeypatch, capsys):
    """Test that --test-order requires Alpaca API credentials."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Clear API keys
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    # Set ENABLE_LIVE_TRADING
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")

    # Mock load_config to return a config (mode override will be applied by main)
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    result = main(["--mode", "live", "--i-understand-live-trading", "--test-order"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires Alpaca API credentials" in captured.err


def test_test_order_success(monkeypatch, capsys):
    """Test that --test-order works correctly with all safety gates passed."""
    from datetime import datetime
    from decimal import Decimal

    from src.app.config import Config
    from src.app.models import Order, OrderSide, OrderStatus, OrderType, Quote

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set all required environment variables
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")

    # Mock load_config to return a config (mode override will be applied by main)
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
        max_order_notional=10000,
        max_positions_notional=50000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    # Mock the broker and quote
    mock_quote = Quote(
        symbol="AAPL",
        bid=Decimal("150.00"),
        ask=Decimal("150.10"),
        last=Decimal("150.05"),
        timestamp=datetime.now(),
    )

    mock_order = Order(
        id="test-order-123",
        symbol="AAPL",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=1,
        price=Decimal("149.99"),
        status=OrderStatus.PENDING,
        submitted_at=datetime.now(),
    )

    mock_broker = MagicMock()
    mock_broker.get_quote.return_value = mock_quote
    mock_broker.submit_order.return_value = mock_order

    with patch("src.app.__main__.AlpacaBroker", return_value=mock_broker):
        result = main(["--mode", "live", "--i-understand-live-trading", "--test-order"])

    assert result == 0
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "TEST ORDER MODE" in captured.out
    assert "LIVE TRADING" in captured.out
    assert "All safety gates passed" in captured.out
    assert "AAPL" in captured.out
    assert "1 share" in captured.out
    assert "TEST ORDER SUBMITTED SUCCESSFULLY" in captured.out
    assert "test-order-123" in captured.out


def test_test_order_fails_risk_check(monkeypatch, capsys):
    """Test that --test-order respects RiskManager checks."""
    from datetime import datetime
    from decimal import Decimal

    from src.app.config import Config
    from src.app.models import Quote

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set all required environment variables
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")

    # Mock load_config  (CLI will override max_order_notional to very low value)
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=Decimal("1000"),
        max_order_notional=Decimal("10000"),
        max_positions_notional=Decimal("50000"),
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    # Mock the broker and quote
    mock_quote = Quote(
        symbol="AAPL",
        bid=Decimal("150.00"),
        ask=Decimal("150.10"),
        last=Decimal("150.05"),
        timestamp=datetime.now(),
    )

    mock_broker = MagicMock()
    mock_broker.get_quote.return_value = mock_quote

    with patch("src.app.__main__.AlpacaBroker", return_value=mock_broker):
        # Use CLI override to set very low limit that will fail the check
        result = main(
            [
                "--mode",
                "live",
                "--i-understand-live-trading",
                "--test-order",
                "--max-order-notional",
                "1",
            ]
        )

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "failed risk check" in captured.err


# Order Management Tests


def test_parse_args_list_open_orders():
    """Test parsing --list-open-orders flag."""
    args = parse_args(["--list-open-orders"])
    assert args.list_open_orders is True


def test_parse_args_list_open_orders_default_false():
    """Test that --list-open-orders defaults to False."""
    args = parse_args([])
    assert args.list_open_orders is False


def test_parse_args_cancel_order_id():
    """Test parsing --cancel-order-id flag."""
    args = parse_args(["--cancel-order-id", "abc-123"])
    assert args.cancel_order_id == "abc-123"


def test_parse_args_cancel_client_order_id():
    """Test parsing --cancel-client-order-id flag."""
    args = parse_args(["--cancel-client-order-id", "client-xyz"])
    assert args.cancel_client_order_id == "client-xyz"


def test_parse_args_replace_order_id():
    """Test parsing --replace-order-id flag."""
    args = parse_args(["--replace-order-id", "order-456"])
    assert args.replace_order_id == "order-456"


def test_parse_args_limit_price():
    """Test parsing --limit-price flag."""
    args = parse_args(["--limit-price", "150.50"])
    assert args.limit_price == 150.50


def test_parse_args_qty():
    """Test parsing --qty flag."""
    args = parse_args(["--qty", "10"])
    assert args.qty == 10


def test_list_open_orders_requires_live_mode(monkeypatch, capsys):
    """Test that --list-open-orders works in paper mode without safety gates."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Mock load_config
    mock_config = Config(
        mode="paper",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
        alpaca_base_url="https://paper-api.alpaca.markets",
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    # Mock AlpacaBroker to avoid needing real credentials
    with patch("src.app.__main__.AlpacaBroker") as mock_broker_cls:
        mock_broker = MagicMock()
        mock_broker.list_open_orders_detailed.return_value = []
        mock_broker_cls.return_value = mock_broker

        result = main(["--mode", "paper", "--list-open-orders"])

        assert result == 0  # Should succeed in paper mode
        mock_loop.assert_not_called()

        captured = capsys.readouterr()
        assert "PAPER MODE" in captured.out


def test_list_open_orders_requires_i_understand_live_trading(monkeypatch, capsys):
    """Test that --list-open-orders requires --i-understand-live-trading."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Mock load_config
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    result = main(["--mode", "live", "--list-open-orders"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires --i-understand-live-trading" in captured.err


def test_list_open_orders_requires_enable_live_trading_env(monkeypatch, capsys):
    """Test that --list-open-orders requires ENABLE_LIVE_TRADING=true."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys but not ENABLE_LIVE_TRADING
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)

    # Mock load_config
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    result = main(["--mode", "live", "--i-understand-live-trading", "--list-open-orders"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires ENABLE_LIVE_TRADING=true" in captured.err


def test_list_open_orders_success(monkeypatch, capsys):
    """Test successful listing of open orders."""
    from datetime import datetime
    from decimal import Decimal

    from src.app.config import Config
    from src.app.models import Order, OrderSide, OrderStatus, OrderType

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set all required environment variables
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")

    # Mock load_config
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL", "MSFT"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    # Mock orders
    mock_orders = [
        Order(
            id="order-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("150.00"),
            status=OrderStatus.PENDING,
            submitted_at=datetime.now(),
            client_order_id="client-1",
        ),
        Order(
            id="order-2",
            symbol="MSFT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            quantity=5,
            price=Decimal("300.00"),
            status=OrderStatus.PENDING,
            submitted_at=datetime.now(),
            client_order_id="client-2",
        ),
    ]

    mock_broker = MagicMock()
    mock_broker.list_open_orders_detailed.return_value = mock_orders

    with patch("src.app.__main__.AlpacaBroker", return_value=mock_broker):
        result = main(["--mode", "live", "--i-understand-live-trading", "--list-open-orders"])

    assert result == 0
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "Open Orders" in captured.out
    assert "AAPL" in captured.out
    assert "MSFT" in captured.out
    assert "order-1" in captured.out
    assert "order-2" in captured.out


def test_cancel_order_requires_live_mode(monkeypatch, capsys):
    """Test that --cancel-order-id works in paper mode without safety gates."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Mock load_config
    mock_config = Config(
        mode="paper",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
        alpaca_base_url="https://paper-api.alpaca.markets",
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    # Mock AlpacaBroker to avoid needing real credentials
    with patch("src.app.__main__.AlpacaBroker") as mock_broker_cls:
        mock_broker = MagicMock()
        mock_broker.cancel_order.return_value = True
        mock_broker_cls.return_value = mock_broker

        result = main(["--mode", "paper", "--cancel-order-id", "abc-123"])

        assert result == 0  # Should succeed in paper mode
        mock_loop.assert_not_called()

        captured = capsys.readouterr()
        assert "PAPER MODE" in captured.out


def test_cancel_order_requires_i_understand_live_trading(monkeypatch, capsys):
    """Test that --cancel-order-id requires --i-understand-live-trading."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Mock load_config
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    result = main(["--mode", "live", "--cancel-order-id", "abc-123"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires --i-understand-live-trading" in captured.err


def test_cancel_order_requires_enable_live_trading_env(monkeypatch, capsys):
    """Test that --cancel-order-id requires ENABLE_LIVE_TRADING=true."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys but not ENABLE_LIVE_TRADING
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)

    # Mock load_config
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    result = main(["--mode", "live", "--i-understand-live-trading", "--cancel-order-id", "abc-123"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires ENABLE_LIVE_TRADING=true" in captured.err


def test_cancel_order_by_id_success(monkeypatch, capsys):
    """Test successful cancellation of order by ID."""
    from datetime import datetime
    from decimal import Decimal

    from src.app.config import Config
    from src.app.models import Order, OrderSide, OrderStatus, OrderType

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set all required environment variables
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")

    # Mock load_config
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    # Mock order after cancellation
    mock_order = Order(
        id="order-123",
        symbol="AAPL",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("150.00"),
        status=OrderStatus.CANCELED,
        submitted_at=datetime.now(),
        client_order_id="client-123",
    )

    mock_broker = MagicMock()
    mock_broker.cancel_order.return_value = True
    mock_broker.get_order_status.return_value = mock_order

    with patch("src.app.__main__.AlpacaBroker", return_value=mock_broker):
        result = main(
            ["--mode", "live", "--i-understand-live-trading", "--cancel-order-id", "order-123"]
        )

    assert result == 0
    mock_loop.assert_not_called()
    mock_broker.cancel_order.assert_called_once_with("order-123")

    captured = capsys.readouterr()
    assert "CANCEL ORDER" in captured.out
    assert "order-123" in captured.out
    assert "CANCELED" in captured.out


def test_cancel_order_by_client_id_success(monkeypatch, capsys):
    """Test successful cancellation of order by client ID."""
    from datetime import datetime
    from decimal import Decimal

    from src.app.config import Config
    from src.app.models import Order, OrderSide, OrderStatus, OrderType

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set all required environment variables
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")

    # Mock load_config
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    # Mock order after cancellation
    mock_order = Order(
        id="order-456",
        symbol="AAPL",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("150.00"),
        status=OrderStatus.CANCELED,
        submitted_at=datetime.now(),
        client_order_id="client-xyz",
    )

    mock_broker = MagicMock()
    mock_broker.cancel_order_by_client_id.return_value = True
    # Return the order ID when asked to find by client ID
    mock_broker.list_open_orders_detailed.return_value = [mock_order]

    with patch("src.app.__main__.AlpacaBroker", return_value=mock_broker):
        result = main(
            [
                "--mode",
                "live",
                "--i-understand-live-trading",
                "--cancel-client-order-id",
                "client-xyz",
            ]
        )

    assert result == 0
    mock_loop.assert_not_called()
    mock_broker.cancel_order_by_client_id.assert_called_once_with("client-xyz")

    captured = capsys.readouterr()
    assert "CANCEL ORDER" in captured.out
    assert "client-xyz" in captured.out


def test_replace_order_requires_live_mode(monkeypatch, capsys):
    """Test that --replace-order-id works in paper mode without safety gates."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Mock load_config - use smaller values to pass risk checks
    mock_config = Config(
        mode="paper",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
        alpaca_base_url="https://paper-api.alpaca.markets",
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    # Mock AlpacaBroker to avoid needing real credentials
    with patch("src.app.__main__.AlpacaBroker") as mock_broker_cls:
        mock_broker = MagicMock()

        # Mock existing order - use small values that pass default risk limits
        existing_order = MagicMock()
        existing_order.symbol = "AAPL"
        existing_order.side = MagicMock()
        existing_order.side.value = "buy"
        existing_order.quantity = 1
        existing_order.price = Decimal("100.00")
        mock_broker.get_order_status.return_value = existing_order

        # Mock new order
        new_order = MagicMock()
        new_order.id = "new-order-id"
        new_order.status = MagicMock()
        new_order.status.value = "new"
        new_order.symbol = "AAPL"
        new_order.side = MagicMock()
        new_order.side.value = "buy"
        new_order.quantity = 1
        new_order.price = Decimal("100.50")
        mock_broker.replace_order.return_value = new_order

        mock_broker_cls.return_value = mock_broker

        result = main(
            ["--mode", "paper", "--replace-order-id", "order-123", "--limit-price", "100.50"]
        )

        assert result == 0  # Should succeed in paper mode
        mock_loop.assert_not_called()

        captured = capsys.readouterr()
        assert "PAPER MODE" in captured.out


def test_replace_order_requires_i_understand_live_trading(monkeypatch, capsys):
    """Test that --replace-order-id requires --i-understand-live-trading."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Mock load_config
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    result = main(["--mode", "live", "--replace-order-id", "order-123", "--limit-price", "150.50"])

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires --i-understand-live-trading" in captured.err


def test_replace_order_requires_enable_live_trading_env(monkeypatch, capsys):
    """Test that --replace-order-id requires ENABLE_LIVE_TRADING=true."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set API keys but not ENABLE_LIVE_TRADING
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)

    # Mock load_config
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    result = main(
        [
            "--mode",
            "live",
            "--i-understand-live-trading",
            "--replace-order-id",
            "order-123",
            "--limit-price",
            "150.50",
        ]
    )

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires ENABLE_LIVE_TRADING=true" in captured.err


def test_replace_order_requires_limit_price(monkeypatch, capsys):
    """Test that --replace-order-id requires --limit-price parameter."""
    from src.app.config import Config

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set all required environment variables
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")

    # Mock load_config
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=1000,
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    result = main(
        ["--mode", "live", "--i-understand-live-trading", "--replace-order-id", "order-123"]
    )

    assert result == 1
    mock_loop.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "requires --limit-price" in captured.err


def test_replace_order_success(monkeypatch, capsys):
    """Test successful order replacement with new limit price."""
    from datetime import datetime
    from decimal import Decimal

    from src.app.config import Config
    from src.app.models import Order, OrderSide, OrderStatus, OrderType

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set all required environment variables
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    # Set risk limits via environment variables to ensure they're used
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "10000")
    monkeypatch.setenv("MAX_POSITIONS_NOTIONAL", "50000")

    # Mock load_config
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=10000,
        max_order_notional=Decimal("10000"),
        max_positions_notional=Decimal("50000"),
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    # Mock existing order (use small values to stay under $500 default limit)
    existing_order = Order(
        id="order-123",
        symbol="AAPL",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=1,
        price=Decimal("100.00"),
        status=OrderStatus.PENDING,
        submitted_at=datetime.now(),
        client_order_id="client-123",
    )

    # Mock new order after replacement
    new_order = Order(
        id="order-456",
        symbol="AAPL",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=1,
        price=Decimal("105.00"),
        status=OrderStatus.PENDING,
        submitted_at=datetime.now(),
        client_order_id="client-456",
    )

    mock_broker = MagicMock()
    mock_broker.get_order_status.return_value = existing_order
    mock_broker.replace_order.return_value = new_order

    with patch("src.app.__main__.AlpacaBroker", return_value=mock_broker):
        result = main(
            [
                "--mode",
                "live",
                "--i-understand-live-trading",
                "--replace-order-id",
                "order-123",
                "--limit-price",
                "105.00",
            ]
        )

    assert result == 0
    mock_loop.assert_not_called()
    mock_broker.replace_order.assert_called_once_with("order-123", Decimal("105.00"), None)

    captured = capsys.readouterr()
    assert "REPLACE ORDER" in captured.out or "ORDER REPLACED" in captured.out
    assert "order-123" in captured.out
    assert "105" in captured.out
    assert "order-456" in captured.out


def test_replace_order_with_quantity_success(monkeypatch, capsys):
    """Test successful order replacement with new limit price and quantity."""
    from datetime import datetime
    from decimal import Decimal

    from src.app.config import Config
    from src.app.models import Order, OrderSide, OrderStatus, OrderType

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set all required environment variables
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    # Set risk limits via environment variables to ensure they're used
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "10000")
    monkeypatch.setenv("MAX_POSITIONS_NOTIONAL", "50000")

    # Mock load_config
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=10000,
        max_order_notional=Decimal("10000"),
        max_positions_notional=Decimal("50000"),
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    # Mock existing order (use small values to stay under $500 default limit)
    existing_order = Order(
        id="order-789",
        symbol="AAPL",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=2,
        price=Decimal("100.00"),
        status=OrderStatus.PENDING,
        submitted_at=datetime.now(),
        client_order_id="client-789",
    )

    # Mock new order after replacement (3 * $95 = $285, under $500 limit)
    new_order = Order(
        id="order-999",
        symbol="AAPL",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=3,
        price=Decimal("95.00"),
        status=OrderStatus.PENDING,
        submitted_at=datetime.now(),
        client_order_id="client-999",
    )

    mock_broker = MagicMock()
    mock_broker.get_order_status.return_value = existing_order
    mock_broker.replace_order.return_value = new_order

    with patch("src.app.__main__.AlpacaBroker", return_value=mock_broker):
        result = main(
            [
                "--mode",
                "live",
                "--i-understand-live-trading",
                "--replace-order-id",
                "order-789",
                "--limit-price",
                "95.00",
                "--qty",
                "3",
            ]
        )

    assert result == 0
    mock_loop.assert_not_called()
    mock_broker.replace_order.assert_called_once_with("order-789", Decimal("95.00"), 3)

    captured = capsys.readouterr()
    assert "REPLACE ORDER" in captured.out or "ORDER REPLACED" in captured.out
    assert "order-789" in captured.out
    assert "95" in captured.out
    assert "3" in captured.out
    assert "order-999" in captured.out


def test_replace_order_fails_risk_check(monkeypatch, capsys):
    """Test that --replace-order-id respects RiskManager checks."""
    from datetime import datetime
    from decimal import Decimal

    from src.app.config import Config
    from src.app.models import Order, OrderSide, OrderStatus, OrderType

    mock_loop = MagicMock()
    monkeypatch.setattr("src.app.__main__.run_trading_loop", mock_loop)

    # Set all required environment variables
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")

    # Mock load_config with very low limits to trigger failure
    mock_config = Config(
        mode="mock",
        allowed_symbols=["AAPL"],
        max_positions=5,
        max_order_quantity=100,
        max_daily_loss=Decimal("10000"),
        max_order_notional=Decimal("10"),  # Very low to cause failure
        max_positions_notional=Decimal("50000"),
    )
    monkeypatch.setattr("src.app.__main__.load_config", lambda: mock_config)

    # Mock existing order
    existing_order = Order(
        id="order-123",
        symbol="AAPL",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("150.00"),
        status=OrderStatus.PENDING,
        submitted_at=datetime.now(),
        client_order_id="client-123",
    )

    mock_broker = MagicMock()
    mock_broker.get_order_status.return_value = existing_order

    with patch("src.app.__main__.AlpacaBroker", return_value=mock_broker):
        result = main(
            [
                "--mode",
                "live",
                "--i-understand-live-trading",
                "--replace-order-id",
                "order-123",
                "--limit-price",
                "150.50",
            ]
        )

    assert result == 1
    mock_loop.assert_not_called()
    mock_broker.replace_order.assert_not_called()

    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert "failed risk check" in captured.err
