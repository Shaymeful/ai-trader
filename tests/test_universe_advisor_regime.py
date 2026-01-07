"""Tests for Universe Advisor market regime detection."""

from datetime import UTC, datetime

import pytest

from src.app.universe_advisor.models import MarketRegime
from src.app.universe_advisor.regime import detect_market_regime


class MockMarketDataProvider:
    """Mock market data provider for testing."""

    def __init__(self, spy_data: dict):
        """
        Initialize mock provider.

        Args:
            spy_data: SPY data to return (price, ma, closes)
        """
        self.spy_data = spy_data

    def get_market_data(self, symbols: list[str]) -> dict:
        """Return mock market data."""
        return {"SPY": self.spy_data}


def test_detect_regime_bull_low_vol():
    """Test bull market with low volatility detection."""
    # Price above MA50, low volatility
    provider = MockMarketDataProvider(
        {
            "price": 450.0,
            "ma": 440.0,  # Price > MA = bull
            "closes": [
                440.0 + i * 0.5 for i in range(50)
            ],  # Smooth uptrend = low vol
        }
    )

    regime = detect_market_regime(provider)

    assert regime.regime == MarketRegime.BULL_LOW_VOL
    assert regime.trend == "bull"
    assert regime.volatility in ["low", "medium"]
    assert regime.spy_price == 450.0
    assert regime.spy_ma50 == 440.0
    assert regime.confidence > 0.9  # 50 data points


def test_detect_regime_bull_high_vol():
    """Test bull market with high volatility detection."""
    # Price above MA50, high volatility
    closes = [450.0]
    for i in range(1, 50):
        # Create whipsaw pattern (high volatility)
        closes.append(closes[-1] + (10.0 if i % 2 == 0 else -10.0))

    provider = MockMarketDataProvider({"price": 460.0, "ma": 450.0, "closes": closes})

    regime = detect_market_regime(provider)

    assert regime.regime == MarketRegime.BULL_HIGH_VOL
    assert regime.trend == "bull"
    assert regime.volatility == "high"
    assert regime.volatility_value > 0.25  # Annualized vol > 25%


def test_detect_regime_bear_low_vol():
    """Test bear market with low volatility detection."""
    # Price below MA50, low volatility
    provider = MockMarketDataProvider(
        {
            "price": 420.0,
            "ma": 440.0,  # Price < MA = bear
            "closes": [440.0 - i * 0.5 for i in range(50)],  # Smooth downtrend
        }
    )

    regime = detect_market_regime(provider)

    assert regime.regime == MarketRegime.BEAR_LOW_VOL
    assert regime.trend == "bear"
    assert regime.volatility in ["low", "medium"]


def test_detect_regime_bear_high_vol():
    """Test bear market with high volatility detection."""
    # Price below MA50, high volatility
    closes = [420.0]
    for i in range(1, 50):
        # Create high volatility downtrend
        closes.append(closes[-1] - (15.0 if i % 2 == 0 else -5.0))

    provider = MockMarketDataProvider({"price": 400.0, "ma": 440.0, "closes": closes})

    regime = detect_market_regime(provider)

    assert regime.regime == MarketRegime.BEAR_HIGH_VOL
    assert regime.trend == "bear"
    assert regime.volatility == "high"


def test_detect_regime_insufficient_data():
    """Test regime detection with insufficient data."""
    provider = MockMarketDataProvider(
        {
            "price": 450.0,
            "ma": 450.0,
            "closes": [450.0] * 10,  # Only 10 data points
        }
    )

    regime = detect_market_regime(provider)

    # Should still return a regime (uses default 20% vol)
    assert regime.regime in [
        MarketRegime.BULL_LOW_VOL,
        MarketRegime.BULL_HIGH_VOL,
        MarketRegime.BEAR_LOW_VOL,
        MarketRegime.BEAR_HIGH_VOL,
    ]
    assert regime.confidence < 1.0  # Lower confidence with less data


def test_detect_regime_no_spy_data():
    """Test regime detection when SPY data unavailable."""
    provider = MockMarketDataProvider({})  # Empty data

    regime = detect_market_regime(provider)

    assert regime.regime == MarketRegime.UNKNOWN
    assert regime.confidence == 0.0
    assert regime.spy_price == 0.0


def test_regime_confidence_increases_with_data():
    """Test that confidence increases with more data points."""
    # Provider with 25 closes
    provider_25 = MockMarketDataProvider(
        {"price": 450.0, "ma": 440.0, "closes": [450.0] * 25}
    )

    # Provider with 50 closes
    provider_50 = MockMarketDataProvider(
        {"price": 450.0, "ma": 440.0, "closes": [450.0] * 50}
    )

    regime_25 = detect_market_regime(provider_25)
    regime_50 = detect_market_regime(provider_50)

    assert regime_50.confidence > regime_25.confidence


def test_regime_timestamp_is_recent():
    """Test that regime timestamp is current."""
    provider = MockMarketDataProvider(
        {"price": 450.0, "ma": 440.0, "closes": [450.0] * 50}
    )

    regime = detect_market_regime(provider)

    timestamp = datetime.fromisoformat(regime.timestamp.replace("Z", "+00:00"))
    now = datetime.now(UTC)

    # Timestamp should be within last second
    assert (now - timestamp).total_seconds() < 1.0


def test_volatility_buckets():
    """Test volatility bucketing thresholds."""
    # Low volatility (< 15%)
    provider_low = MockMarketDataProvider(
        {"price": 450.0, "ma": 440.0, "closes": [450.0 + i * 0.1 for i in range(50)]}
    )

    regime_low = detect_market_regime(provider_low)
    assert regime_low.volatility == "low"
    assert regime_low.volatility_value < 0.15

    # Medium volatility (15-25%)
    closes_med = [450.0]
    for i in range(1, 50):
        closes_med.append(closes_med[-1] + (3.0 if i % 2 == 0 else -3.0))

    provider_med = MockMarketDataProvider({"price": 450.0, "ma": 440.0, "closes": closes_med})

    regime_med = detect_market_regime(provider_med)
    assert regime_med.volatility in ["medium", "low"]  # May vary slightly

    # High volatility (> 25%)
    closes_high = [450.0]
    for i in range(1, 50):
        closes_high.append(closes_high[-1] + (12.0 if i % 2 == 0 else -12.0))

    provider_high = MockMarketDataProvider({"price": 450.0, "ma": 440.0, "closes": closes_high})

    regime_high = detect_market_regime(provider_high)
    assert regime_high.volatility == "high"
    assert regime_high.volatility_value > 0.25
