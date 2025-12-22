"""Tests for CLI interface."""

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
