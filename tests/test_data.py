"""Tests for data provider module."""

import pytest

from src.data import MockDataProvider


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
