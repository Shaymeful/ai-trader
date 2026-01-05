"""Simple mean reversion strategy based on z-score or RSI."""

from .base import PositionIntent, Strategy


class MeanReversionStrategy(Strategy):
    """
    Simple mean reversion strategy.

    Logic:
    - If z-score < -1.0 (oversold) => go long (target 1 share)
    - If z-score > 1.0 (overbought) => flat (target 0 shares)
    - Otherwise => flat

    This is a simplified strategy for shadow mode testing.
    In production, you'd use more sophisticated mean reversion signals.
    """

    def __init__(self, zscore_threshold: float = 1.0):
        """
        Initialize mean reversion strategy.

        Args:
            zscore_threshold: Z-score threshold for entry/exit signals
        """
        super().__init__(name=f"MeanRev_Z{zscore_threshold}")
        self.zscore_threshold = zscore_threshold

    def generate_intents(
        self,
        universe: list[str],
        market_data: dict,
        candidate_map: dict[str, str] | None = None,
    ) -> list[PositionIntent]:
        """
        Generate position intents based on z-score mean reversion.

        Args:
            universe: List of symbols to analyze
            market_data: Dictionary with price and z-score data
                Example: {"SPY": {"price": 450.0, "zscore": -1.5}}
            candidate_map: Optional mapping of symbol -> candidate_id

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
            zscore = data.get("zscore")

            # Skip if missing data
            if price is None or zscore is None:
                continue

            # Get candidate_id if available
            candidate_id = candidate_map.get(symbol) if candidate_map else None

            # Mean reversion logic
            if zscore < -self.zscore_threshold:
                # Oversold: potential bounce
                conviction = min(1.0, abs(zscore) / 2.0)  # Higher conviction for extreme moves
                intents.append(
                    PositionIntent(
                        symbol=symbol,
                        target_quantity=1,  # Fixed 1 share for simplicity
                        conviction=conviction,
                        reason=f"Oversold: z-score {zscore:.2f} < {-self.zscore_threshold}",
                        candidate_id=candidate_id,
                    )
                )
            elif zscore > self.zscore_threshold:
                # Overbought: exit or stay flat
                intents.append(
                    PositionIntent(
                        symbol=symbol,
                        target_quantity=0,  # Flat
                        conviction=0.0,
                        reason=f"Overbought: z-score {zscore:.2f} > {self.zscore_threshold}",
                        candidate_id=candidate_id,
                    )
                )
            else:
                # Neutral zone: stay flat
                intents.append(
                    PositionIntent(
                        symbol=symbol,
                        target_quantity=0,  # Flat
                        conviction=0.0,
                        reason=f"Neutral: z-score {zscore:.2f} in range [{-self.zscore_threshold}, {self.zscore_threshold}]",
                        candidate_id=candidate_id,
                    )
                )

        return intents
