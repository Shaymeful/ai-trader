"""Hourly market data provider using Alpaca API."""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import timedelta

from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from .base import MarketDataProvider


class HourlyMarketDataProvider(MarketDataProvider):
    """
    Market data provider that fetches hourly bars from Alpaca.

    Fetches the last N hourly bars and calculates:
    - Latest close price
    - Moving average (MA)
    - Z-score for mean reversion
    """

    def __init__(self, api_key: str, secret_key: str, lookback_bars: int = 50, ma_period: int = 20):
        """
        Initialize hourly market data provider.

        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            lookback_bars: Number of hourly bars to fetch (default 50)
            ma_period: Period for moving average calculation (default 20)
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.lookback_bars = lookback_bars
        self.ma_period = ma_period
        self.logger = logging.getLogger("ai-trader")

        # Initialize Alpaca data client
        from alpaca.data import StockHistoricalDataClient

        self.client = StockHistoricalDataClient(api_key, secret_key)

    def get_market_data(self, symbols: list[str]) -> dict[str, dict]:
        """
        Fetch hourly bars and calculate indicators.

        Args:
            symbols: List of symbols to fetch

        Returns:
            Dictionary mapping symbol to market data with price, ma, zscore
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # Calculate time window for hourly bars
        # End at current time, start N days back to ensure we get enough hourly bars
        eastern = ZoneInfo("America/New_York")
        end = datetime.now(eastern)

        # Go back enough days to ensure we get the required number of hourly bars
        # Market hours: 9:30 AM - 4:00 PM ET (6.5 hours/day)
        # Need ~8 trading days to get 50 hourly bars
        days_back = max(15, self.lookback_bars // 5)
        start = end - timedelta(days=days_back)

        # Request hourly bars from Alpaca with timeout
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=TimeFrame.Hour,
                start=start,
                end=end,
                feed="iex",  # IEX feed for paper/free tier
            )

            # Wrap API call with timeout to prevent hanging
            # Use ThreadPoolExecutor to run with timeout (works cross-platform)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.client.get_stock_bars, request)
                try:
                    bars_response = future.result(timeout=30)  # 30 second timeout
                except FuturesTimeoutError:
                    self.logger.error(f"Timeout fetching bars from Alpaca (30s limit exceeded)")
                    self.logger.warning(
                        f"Symbols requested: {', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}"
                    )
                    return {}
        except Exception as e:
            self.logger.error(f"Failed to fetch bars from Alpaca: {e}")
            return {}

        # Process bars for each symbol
        result = {}
        for symbol in symbols:
            alpaca_bars = bars_response.data.get(symbol, [])

            if not alpaca_bars:
                self.logger.warning(f"{symbol}: No hourly bars returned")
                continue

            # Convert to list and sort by timestamp
            bars_list = list(alpaca_bars)
            bars_list.sort(key=lambda b: b.timestamp)

            # Take most recent lookback_bars
            recent_bars = bars_list[-self.lookback_bars :]

            if len(recent_bars) < self.ma_period:
                self.logger.warning(
                    f"{symbol}: Insufficient bars ({len(recent_bars)}) for MA calculation "
                    f"(need {self.ma_period})"
                )
                continue

            # Extract close prices
            closes = [float(bar.close) for bar in recent_bars]

            # Calculate latest price
            latest_price = closes[-1]

            # Calculate moving average (using last ma_period bars)
            ma_closes = closes[-self.ma_period :]
            ma = sum(ma_closes) / len(ma_closes)

            # Calculate z-score (standardized return)
            # Z-score = (current_price - mean) / std_dev
            mean_price = sum(closes) / len(closes)
            variance = sum((p - mean_price) ** 2 for p in closes) / len(closes)
            std_dev = variance**0.5

            zscore = (latest_price - mean_price) / std_dev if std_dev > 0 else 0.0

            result[symbol] = {
                "price": round(latest_price, 2),
                "ma": round(ma, 2),
                "zscore": round(zscore, 2),
                "bars_count": len(recent_bars),
                "closes": closes,  # For Shadow PnL return calculation
            }

            self.logger.info(
                f"{symbol}: price={latest_price:.2f}, ma={ma:.2f}, zscore={zscore:.2f}, "
                f"bars={len(recent_bars)}"
            )

        return result


class MockMarketDataProvider(MarketDataProvider):
    """
    Mock market data provider for offline testing.

    Generates deterministic mock data without network calls.
    """

    def __init__(self, seed: int = 42):
        """
        Initialize mock provider.

        Args:
            seed: Random seed for reproducible data
        """
        import random

        self.seed = seed
        random.seed(seed)

    def get_market_data(self, symbols: list[str]) -> dict[str, dict]:
        """
        Generate mock market data.

        Args:
            symbols: List of symbols

        Returns:
            Dictionary with mock price, ma, zscore, and closes array
        """
        import random

        random.seed(self.seed)

        result = {}
        for symbol in symbols:
            base_price = random.uniform(50, 500)
            ma = base_price * random.uniform(0.95, 1.05)
            zscore = random.uniform(-2.0, 2.0)

            # Generate mock closes array (50 bars with small random changes)
            closes = []
            price = base_price * 0.95  # Start lower
            for _ in range(50):
                price *= 1.0 + random.uniform(-0.01, 0.01)  # +/- 1% per bar
                closes.append(price)

            result[symbol] = {
                "price": round(closes[-1], 2),  # Latest close
                "ma": round(ma, 2),
                "zscore": round(zscore, 2),
                "bars_count": 50,  # Fake sufficient bars
                "closes": closes,  # For Shadow PnL
            }

        return result
