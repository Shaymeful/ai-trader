"""Market data provider abstraction and implementations."""

import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal

from src.app.models import Bar


class DataProvider(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def get_latest_bars(self, symbols: list[str], limit: int = 1) -> dict[str, list[Bar]]:
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

    def get_latest_bars(self, symbols: list[str], limit: int = 1) -> dict[str, list[Bar]]:
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
                    volume=volume,
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
            base_url: Alpaca API base URL (not used by data client, but kept for consistency)
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url

        # Initialize Alpaca data client
        from alpaca.data import StockHistoricalDataClient

        self.client = StockHistoricalDataClient(api_key, secret_key)

    def get_latest_bars(self, symbols: list[str], limit: int = 1) -> dict[str, list[Bar]]:
        """
        Get latest bars from Alpaca API using window ending at most recent market close.

        Args:
            symbols: List of symbols to fetch
            limit: Number of bars to fetch per symbol

        Returns:
            Dictionary mapping symbol to list of bars
        """
        import logging
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        logger = logging.getLogger("ai-trader")

        # Calculate window ending at most recent market close (4:00 PM ET)
        eastern = ZoneInfo("America/New_York")
        now = datetime.now(eastern)

        # Set end to 4:00 PM ET today
        end = now.replace(hour=16, minute=0, second=0, microsecond=0)

        # If current time is before 4:00 PM today, use yesterday's close
        if now < end:
            end -= timedelta(days=1)

        # Skip back over weekends (Saturday=5, Sunday=6)
        while end.weekday() >= 5:
            end -= timedelta(days=1)

        # Start = 5 days before end
        start = end - timedelta(days=5)

        # Request bar data for all symbols with explicit time range
        # Use IEX feed for free/paper accounts (SIP requires paid subscription)
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
            feed="iex",  # IEX feed is available for free tier
        )

        # Fetch bars from Alpaca
        bars_response = self.client.get_stock_bars(request)

        # Convert Alpaca bars to our Bar model
        result = {}
        for symbol in symbols:
            bars_list = []
            # Access the data attribute which contains the dict of bars
            alpaca_bars = bars_response.data.get(symbol, [])

            if alpaca_bars:
                # Convert to list and sort by timestamp (ascending)
                alpaca_bars_list = list(alpaca_bars)
                alpaca_bars_list.sort(key=lambda b: b.timestamp)

                # Take only the most recent 'limit' bars
                for alpaca_bar in alpaca_bars_list[-limit:]:
                    bar = Bar(
                        symbol=symbol,
                        timestamp=alpaca_bar.timestamp.replace(
                            tzinfo=None
                        ),  # Remove timezone for consistency
                        open=Decimal(str(alpaca_bar.open)),
                        high=Decimal(str(alpaca_bar.high)),
                        low=Decimal(str(alpaca_bar.low)),
                        close=Decimal(str(alpaca_bar.close)),
                        volume=alpaca_bar.volume,
                    )
                    bars_list.append(bar)

            # Log diagnostic info
            if bars_list:
                logger.info(f"{symbol}: {len(bars_list)} bar(s) received (requested {limit})")
            else:
                logger.warning(
                    f"{symbol}: 0 bars returned for {start.strftime('%Y-%m-%d %H:%M %Z')} -> "
                    f"{end.strftime('%Y-%m-%d %H:%M %Z')} (may be delisted or invalid symbol)"
                )

            result[symbol] = bars_list

        return result
