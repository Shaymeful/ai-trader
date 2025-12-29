"""Base interface for market data providers used by strategy runner."""

from abc import ABC, abstractmethod


class MarketDataProvider(ABC):
    """
    Abstract base class for market data providers.

    Provides market data in a format suitable for strategy consumption,
    including derived indicators (moving averages, z-scores).
    """

    @abstractmethod
    def get_market_data(self, symbols: list[str]) -> dict[str, dict]:
        """
        Fetch market data and indicators for given symbols.

        Args:
            symbols: List of symbols to fetch data for

        Returns:
            Dictionary mapping symbol to market data dict.
            Each market data dict contains:
                - "price": float - Latest close price
                - "ma": float - Moving average (20-period by default)
                - "zscore": float - Z-score for mean reversion
                - "bars_count": int - Number of bars available (optional)

            If insufficient data is available for a symbol, it may be
            omitted from the result or included with None values.
        """
        pass
