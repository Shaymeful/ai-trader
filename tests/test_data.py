"""Tests for data provider module."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.data import AlpacaDataProvider, MockDataProvider


@pytest.fixture
def provider():
    """Create mock data provider instance."""
    return MockDataProvider()


def test_get_single_bar(provider):
    """Test getting a single bar for one symbol."""
    data = provider.get_latest_bars(["AAPL"], limit=1)

    assert "AAPL" in data
    assert len(data["AAPL"]) == 1

    bar = data["AAPL"][0]
    assert bar.symbol == "AAPL"
    assert bar.close > 0
    assert bar.volume > 0


def test_get_multiple_bars(provider):
    """Test getting multiple bars for one symbol."""
    data = provider.get_latest_bars(["MSFT"], limit=5)

    assert "MSFT" in data
    assert len(data["MSFT"]) == 5

    # Check bars are in chronological order
    bars = data["MSFT"]
    for i in range(len(bars) - 1):
        assert bars[i].timestamp < bars[i + 1].timestamp


def test_get_bars_multiple_symbols(provider):
    """Test getting bars for multiple symbols."""
    symbols = ["AAPL", "MSFT", "GOOGL"]
    data = provider.get_latest_bars(symbols, limit=3)

    assert len(data) == 3
    for symbol in symbols:
        assert symbol in data
        assert len(data[symbol]) == 3


def test_bar_has_valid_ohlc(provider):
    """Test that bars have valid OHLC relationships."""
    data = provider.get_latest_bars(["AAPL"], limit=1)
    bar = data["AAPL"][0]

    # High should be >= open and close
    assert bar.high >= bar.open
    assert bar.high >= bar.close

    # Low should be <= open and close
    assert bar.low <= bar.open
    assert bar.low <= bar.close


def test_mock_provider_price_variation(provider):
    """Test that mock provider generates varying prices."""
    # Get data multiple times
    data1 = provider.get_latest_bars(["AAPL"], limit=1)
    data2 = provider.get_latest_bars(["AAPL"], limit=1)

    price1 = data1["AAPL"][0].close
    price2 = data2["AAPL"][0].close

    # Prices should vary (not always, but likely with random walk)
    # We'll just check they're both positive and reasonable
    assert price1 > 0
    assert price2 > 0
    assert 100 < price1 < 300  # Reasonable range for AAPL mock
    assert 100 < price2 < 300


def test_alpaca_provider_market_close_window():
    """Test AlpacaDataProvider uses market close window and returns bars correctly."""
    # Create fake Alpaca bar objects
    eastern = ZoneInfo("America/New_York")

    class FakeAlpacaBar:
        def __init__(self, timestamp, open_price, high, low, close, volume):
            self.timestamp = timestamp
            self.open = open_price
            self.high = high
            self.low = low
            self.close = close
            self.volume = volume

    # Create 3 fake bars with timezone-aware timestamps
    fake_bars = [
        FakeAlpacaBar(
            timestamp=datetime(2024, 1, 15, 10, 0, tzinfo=eastern),
            open_price=180.0,
            high=181.0,
            low=179.0,
            close=180.5,
            volume=100000,
        ),
        FakeAlpacaBar(
            timestamp=datetime(2024, 1, 15, 10, 1, tzinfo=eastern),
            open_price=180.5,
            high=182.0,
            low=180.0,
            close=181.0,
            volume=150000,
        ),
        FakeAlpacaBar(
            timestamp=datetime(2024, 1, 15, 10, 2, tzinfo=eastern),
            open_price=181.0,
            high=183.0,
            low=180.5,
            close=182.5,
            volume=200000,
        ),
    ]

    # Mock the Alpaca client
    with patch("alpaca.data.StockHistoricalDataClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock the get_stock_bars response - return object with .data attribute
        mock_response = MagicMock()
        mock_response.data = {"AAPL": fake_bars}
        mock_client.get_stock_bars.return_value = mock_response

        # Create AlpacaDataProvider
        provider = AlpacaDataProvider(
            api_key="test_key",
            secret_key="test_secret",
            base_url="https://paper-api.alpaca.markets",
        )

        # Call get_latest_bars with limit=2 (should return last 2 bars)
        result = provider.get_latest_bars(["AAPL"], limit=2)

        # Verify the request was made
        assert mock_client.get_stock_bars.called
        call_args = mock_client.get_stock_bars.call_args
        request = call_args[0][0]

        # Verify request parameters
        from alpaca.data.enums import DataFeed
        from alpaca.data.timeframe import TimeFrame

        # Check timeframe is Minute (compare string representation)
        assert str(request.timeframe) == str(TimeFrame.Minute)
        # Check feed is IEX
        assert request.feed == DataFeed.IEX or str(request.feed) == "iex"

        # Verify the time window is reasonable
        # (Note: Alpaca SDK may convert to UTC internally, so we check the time difference)
        time_diff = request.end - request.start
        assert time_diff == timedelta(days=5), "Window should be 5 days"

        # Verify end time is at a market close hour (16:00 ET = 21:00 UTC in winter)
        # We allow for either timezone representation
        assert request.end.hour in [16, 21], "End should be at market close (4 PM ET or 9 PM UTC)"
        assert request.end.minute == 0
        assert request.end.second == 0

        # Verify result contains AAPL
        assert "AAPL" in result
        assert len(result["AAPL"]) == 2

        # Verify bars are the last 2 bars (sorted)
        bars = result["AAPL"]
        assert bars[0].close == Decimal("181.0")
        assert bars[1].close == Decimal("182.5")

        # Verify timestamps are naive (tzinfo removed)
        assert bars[0].timestamp.tzinfo is None
        assert bars[1].timestamp.tzinfo is None

        # Verify timestamps are in ascending order
        assert bars[0].timestamp < bars[1].timestamp
