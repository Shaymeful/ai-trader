"""Simple trend-following strategy based on moving average."""

from .base import PositionIntent, Strategy


class TrendStrategy(Strategy):
    """
    Simple trend-following strategy.

    Logic:
    - If price > moving average => go long (target 1 share)
    - If price <= moving average => flat (target 0 shares)

    This is a simplified strategy for shadow mode testing.
    In production, you'd use more sophisticated signals and position sizing.
    """

    def __init__(self, ma_period: int = 20):
        """
        Initialize trend strategy.

        Args:
            ma_period: Moving average period for trend detection
        """
        super().__init__(name=f"Trend_MA{ma_period}")
        self.ma_period = ma_period

    def generate_intents(self, universe: list[str], market_data: dict) -> list[PositionIntent]:
        """
        Generate position intents based on price vs moving average.

        Args:
            universe: List of symbols to analyze
            market_data: Dictionary with price and MA data
                Example: {"SPY": {"price": 450.0, "ma": 445.0}}

        Returns:
            List of PositionIntent objects
        """
        intents = []

        for symbol in universe:
            # Skip if no data available
            if symbol not in market_data:
                continue

            data = market_data[symbol]
            price = data.get("price")
            ma = data.get("ma")

            # Skip if missing price or MA
            if price is None or ma is None:
                continue

            # Simple trend logic
            if price > ma:
                # Bullish: price above MA
                conviction = min(1.0, (price - ma) / ma)  # Normalized conviction
                intents.append(
                    PositionIntent(
                        symbol=symbol,
                        target_quantity=1,  # Fixed 1 share for simplicity
                        conviction=conviction,
                        reason=f"Price {price:.2f} > MA({self.ma_period}) {ma:.2f}",
                    )
                )
            else:
                # Bearish or neutral: price at or below MA
                intents.append(
                    PositionIntent(
                        symbol=symbol,
                        target_quantity=0,  # Flat
                        conviction=0.0,
                        reason=f"Price {price:.2f} <= MA({self.ma_period}) {ma:.2f}",
                    )
                )

        return intents
