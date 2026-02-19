"""Multi-factor sentiment scoring for RSS candidates.

Combines RSS confidence, momentum, and volume signals into unified sentiment score.
Used by aggressive_small_mid_sentiment mode for small/mid-cap automation and energy stocks.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class SentimentScorer:
    """Multi-factor sentiment scorer for RSS candidates."""

    def __init__(
        self,
        alpaca_client: Any | None = None,
        rss_weight: float = 0.4,
        momentum_weight: float = 0.3,
        volume_weight: float = 0.3,
    ):
        """Initialize sentiment scorer.

        Args:
            alpaca_client: Alpaca client for market data (optional)
            rss_weight: Weight for RSS confidence component (default: 0.4)
            momentum_weight: Weight for momentum component (default: 0.3)
            volume_weight: Weight for volume component (default: 0.3)
        """
        self.alpaca_client = alpaca_client
        self.rss_weight = rss_weight
        self.momentum_weight = momentum_weight
        self.volume_weight = volume_weight

        # Validate weights sum to 1.0
        total_weight = rss_weight + momentum_weight + volume_weight
        if abs(total_weight - 1.0) > 0.001:
            msg = f"Weights must sum to 1.0, got {total_weight}"
            raise ValueError(msg)

    def compute_sentiment_score(
        self, symbol: str, text: str, rss_confidence: float
    ) -> tuple[float, dict[str, float]]:
        """Compute combined sentiment score from multiple factors.

        Args:
            symbol: Stock symbol
            text: Headline/description text
            rss_confidence: Base RSS confidence (0.0-1.0)

        Returns:
            (combined_score, factors_dict) tuple
            - combined_score: Weighted combination of all factors (-1.0 to 1.0)
            - factors_dict: Individual factor scores for debugging
        """
        # RSS confidence is already 0.0-1.0, scale to -1.0 to 1.0
        rss_score = (rss_confidence * 2.0) - 1.0

        # Compute momentum score
        momentum_score = self._compute_momentum(symbol)

        # Compute volume surge score
        volume_score = self._compute_volume_surge(symbol)

        # Weighted combination
        combined = (
            (rss_score * self.rss_weight)
            + (momentum_score * self.momentum_weight)
            + (volume_score * self.volume_weight)
        )

        # Clamp to [-1.0, 1.0]
        combined = max(-1.0, min(1.0, combined))

        factors = {
            "combined": round(combined, 4),
            "rss": round(rss_score, 4),
            "momentum": round(momentum_score, 4),
            "volume": round(volume_score, 4),
        }

        return combined, factors

    def _compute_momentum(self, symbol: str) -> float:
        """Compute momentum score from price action.

        Compares 5-day SMA vs 20-day SMA:
        - Positive momentum: 5-day > 20-day → score toward +1.0
        - Negative momentum: 5-day < 20-day → score toward -1.0

        Args:
            symbol: Stock symbol

        Returns:
            Momentum score (-1.0 to 1.0), 0.0 if data unavailable
        """
        if not self.alpaca_client:
            return 0.0  # Neutral if no market data available

        try:
            # Fetch 25 days of bars (need 20 for SMA, plus buffer)
            end = datetime.now()
            start = end - timedelta(days=30)

            bars = self.alpaca_client.get_bars(
                symbol=symbol,
                timeframe="1Day",
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                limit=30,
            )

            if not bars or len(bars) < 20:
                return 0.0  # Not enough data

            # Extract closing prices
            closes = [bar.c for bar in bars]

            if len(closes) < 20:
                return 0.0

            # Compute SMAs
            sma_5 = sum(closes[-5:]) / 5
            sma_20 = sum(closes[-20:]) / 20

            # Compute momentum score (percentage difference)
            pct_diff = (sma_5 - sma_20) / sma_20

            # Scale to [-1.0, 1.0] (clip at +/- 10% difference)
            score = pct_diff / 0.10  # 10% difference = 1.0 score
            score = max(-1.0, min(1.0, score))

            return score

        except Exception:
            # Silently handle errors (missing symbol, API errors)
            return 0.0

    def _compute_volume_surge(self, symbol: str) -> float:
        """Compute volume surge score.

        Compares 3-day avg volume vs 20-day avg volume:
        - High volume surge: recent volume >> avg → score toward +1.0
        - Low volume: recent volume << avg → score toward -1.0

        Args:
            symbol: Stock symbol

        Returns:
            Volume score (-1.0 to 1.0), 0.0 if data unavailable
        """
        if not self.alpaca_client:
            return 0.0  # Neutral if no market data available

        try:
            # Fetch 25 days of bars (need 20 for avg, plus buffer)
            end = datetime.now()
            start = end - timedelta(days=30)

            bars = self.alpaca_client.get_bars(
                symbol=symbol,
                timeframe="1Day",
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                limit=30,
            )

            if not bars or len(bars) < 20:
                return 0.0  # Not enough data

            # Extract volumes
            volumes = [bar.v for bar in bars]

            if len(volumes) < 20:
                return 0.0

            # Compute averages
            recent_3day = sum(volumes[-3:]) / 3
            avg_20day = sum(volumes[-20:]) / 20

            if avg_20day == 0:
                return 0.0

            # Compute volume ratio
            ratio = recent_3day / avg_20day

            # Scale to [-1.0, 1.0]
            # ratio < 0.5 → -1.0 (very low volume)
            # ratio = 1.0 → 0.0 (normal volume)
            # ratio > 2.0 → +1.0 (high volume surge)
            if ratio < 1.0:
                # Map [0.5, 1.0] to [-1.0, 0.0]
                score = (ratio - 1.0) / 0.5
            else:
                # Map [1.0, 2.0] to [0.0, 1.0]
                score = (ratio - 1.0) / 1.0

            # Clamp to [-1.0, 1.0]
            score = max(-1.0, min(1.0, score))

            return score

        except Exception:
            # Silently handle errors (missing symbol, API errors)
            return 0.0
