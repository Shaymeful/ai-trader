"""Market data provider abstraction and implementations."""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List
import random

from src.app.models import Bar


class DataProvider(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def get_latest_bars(self, symbols: List[str], limit: int = 1) -> dict[str, List[Bar]]:
        """
        Get latest bars for given symbols.

        Args:
            symbols: List of symbols to fetch
            limit: Number of bars to fetch per symbol

        Returns:
            Dictionary mapping symbol to list of bars
        """
        pass


class MockDataProvider(DataProvider):
    """Mock data provider for offline testing."""

    def __init__(self):
        self.call_count = 0

    def get_latest_bars(self, symbols: List[str], limit: int = 1) -> dict[str, List[Bar]]:
        """
        Generate mock bars with simulated price movement.

        Creates synthetic data with realistic-looking price movements
        for offline testing.
        """
        self.call_count += 1
        result = {}

        base_prices = {
            "AAPL": 180.0,
            "MSFT": 380.0,
            "GOOGL": 140.0,
            "AMZN": 170.0,
            "TSLA": 250.0,
        }

        for symbol in symbols:
            bars = []
            base_price = base_prices.get(symbol, 100.0)

            # Add some variation based on call count to simulate movement
            price_drift = (self.call_count % 20 - 10) * 0.5

            for i in range(limit):
                # Generate bars from oldest to newest
                # Use a Monday at 10 AM for testing (weekday during market hours)
                base_time = datetime(2024, 1, 15, 10, 0)  # Monday 10:00 AM
                timestamp = base_time + timedelta(minutes=i)

                # Random walk around base price
                variation = random.uniform(-2.0, 2.0)
                close_price = base_price + price_drift + variation

                open_price = close_price + random.uniform(-0.5, 0.5)
                high_price = max(open_price, close_price) + random.uniform(0, 1.0)
                low_price = min(open_price, close_price) - random.uniform(0, 1.0)
                volume = random.randint(100000, 1000000)

                bar = Bar(
                    symbol=symbol,
                    timestamp=timestamp,
                    open=Decimal(str(round(open_price, 2))),
                    high=Decimal(str(round(high_price, 2))),
                    low=Decimal(str(round(low_price, 2))),
                    close=Decimal(str(round(close_price, 2))),
                    volume=volume
                )
                bars.append(bar)

            result[symbol] = bars

        return result


class AlpacaDataProvider(DataProvider):
    """Alpaca market data provider."""

    def __init__(self, api_key: str, secret_key: str, base_url: str):
        """
        Initialize Alpaca data provider.

        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            base_url: Alpaca API base URL
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url

        # Note: In a real implementation, you would use the alpaca-py library here
        # For this MVP, we keep it simple and just store credentials
        # Actual implementation would import: from alpaca.data import StockHistoricalDataClient

    def get_latest_bars(self, symbols: List[str], limit: int = 1) -> dict[str, List[Bar]]:
        """
        Get latest bars from Alpaca API.

        Args:
            symbols: List of symbols to fetch
            limit: Number of bars to fetch per symbol

        Returns:
            Dictionary mapping symbol to list of bars

        Note:
            This is a placeholder. Real implementation would use alpaca-py library:

            from alpaca.data import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            client = StockHistoricalDataClient(self.api_key, self.secret_key)
            request = StockBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=TimeFrame.Minute,
                limit=limit
            )
            bars_data = client.get_stock_bars(request)
            # Convert to our Bar model...
        """
        # Placeholder - would require alpaca-py library
        raise NotImplementedError(
            "Alpaca data provider requires alpaca-py library. "
            "Use MockDataProvider for offline testing."
        )
