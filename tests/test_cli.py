"""Tests for CLI interface."""

from unittest.mock import MagicMock

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
