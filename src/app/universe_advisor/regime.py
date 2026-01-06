"""Market regime detection using SPY trend + volatility."""

import statistics
from datetime import UTC, datetime

from src.app.data_providers.base import MarketDataProvider

from .models import MarketRegime, RegimeData


def detect_market_regime(provider: MarketDataProvider) -> RegimeData:
    """
    Detect market regime using SPY trend + volatility.

    Args:
        provider: Market data provider

    Returns:
        RegimeData with classification
    """
    # Get SPY data
    market_data = provider.get_market_data(["SPY"])
    spy_data = market_data.get("SPY")

    if not spy_data:
        return RegimeData(
            regime=MarketRegime.UNKNOWN,
            spy_price=0.0,
            spy_ma50=0.0,
            trend="bear",
            volatility="high",
            volatility_value=0.0,
            confidence=0.0,
            timestamp=datetime.now(UTC).isoformat(),
        )

    spy_price = spy_data["price"]
    spy_ma50 = spy_data.get("ma", spy_price)  # Fallback if MA not available

    # Detect trend
    trend = "bull" if spy_price >= spy_ma50 else "bear"

    # Calculate volatility (20-day rolling std-dev of returns)
    closes = spy_data.get("closes", [])
    if len(closes) >= 20:
        returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, 20)]
        std_dev = statistics.stdev(returns)
        # Annualize: multiply by sqrt(252 trading days)
        annualized_vol = std_dev * (252**0.5)
    else:
        annualized_vol = 0.20  # Default 20% if insufficient data

    # Bucket volatility
    if annualized_vol < 0.15:
        volatility = "low"
    elif annualized_vol < 0.25:
        volatility = "medium"
    else:
        volatility = "high"

    # Combine into regime
    if trend == "bull" and volatility in ["low", "medium"]:
        regime = MarketRegime.BULL_LOW_VOL
    elif trend == "bull" and volatility == "high":
        regime = MarketRegime.BULL_HIGH_VOL
    elif trend == "bear" and volatility in ["low", "medium"]:
        regime = MarketRegime.BEAR_LOW_VOL
    else:  # bear + high volatility
        regime = MarketRegime.BEAR_HIGH_VOL

    # Confidence based on data quality
    confidence = min(1.0, len(closes) / 50.0)  # Higher with more data

    return RegimeData(
        regime=regime,
        spy_price=spy_price,
        spy_ma50=spy_ma50,
        trend=trend,
        volatility=volatility,
        volatility_value=annualized_vol,
        confidence=confidence,
        timestamp=datetime.now(UTC).isoformat(),
    )
