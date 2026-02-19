"""AI Co-Pilot Weighted Strategy: Config-driven per-sector ticker allocation.

This strategy implements a weighted portfolio allocation across sectors and tickers,
using per-sector ticker weights from configuration to generate position intents.

Key Features:
- Per-sector ticker weights (e.g., NVDA: 25% of strategy budget)
- Automatic weight normalization (ensures full budget utilization)
- Active universe filtering (only trades symbols in active sectors)
- Execution guardrail (execution_enabled=false prevents trading)
- Conviction-based allocation (weight encoded as conviction field)

Design Rationale:
- Strategies don't receive allocated budget → encode weight as conviction field
- Strategies don't receive current positions → return absolute targets (phase 1)
- Executor handles reconciliation and generates delta orders
- Allocator scales intents by: strategy_budget × conviction × normalized_weight
"""

from .base import PositionIntent, Strategy


class AICopilotWeightedStrategy(Strategy):
    """
    AI Co-Pilot weighted portfolio strategy.

    Uses per-sector ticker weights to allocate capital across configured symbols.
    Integrates with existing allocation/netting/execution pipeline.

    Example Config:
        per_sector_weights:
            mega_cap_tech:
                NVDA: 0.25  # 25% of strategy allocation
                MSFT: 0.15
                AAPL: 0.10
            us_sector_etfs:
                XLF: 0.20
                XLE: 0.15

    Weight Encoding:
        - Weights don't need to sum to 1.0 (strategy normalizes automatically)
        - Conviction field encodes normalized weight (allocator multiplies by budget)
        - Target quantity = 1 (fixed, allocator scales by conviction)
    """

    def __init__(
        self,
        per_sector_weights: dict[str, dict[str, float]],
        execution_enabled: bool = False,
        rebalance_threshold_pct: float = 0.02,
        allow_shorts: bool = False,
        sentiment_adjustment_enabled: bool = False,
    ):
        """
        Initialize AI Co-Pilot Weighted Strategy.

        Args:
            per_sector_weights: Nested dict of sector -> {ticker: weight}
                Example: {"mega_cap_tech": {"NVDA": 0.25, "MSFT": 0.15}}
            execution_enabled: Safety guardrail - must be true to trade
            rebalance_threshold_pct: Reserved for phase 2 (smart rebalancing)
            allow_shorts: Reserved for phase 2 (short positions)
            sentiment_adjustment_enabled: Enable sentiment-based weight adjustment
        """
        super().__init__(name="AI_COPILOT_WEIGHTED")
        self.per_sector_weights = per_sector_weights or {}
        self.execution_enabled = execution_enabled
        self.rebalance_threshold_pct = rebalance_threshold_pct
        self.allow_shorts = allow_shorts
        self.sentiment_adjustment_enabled = sentiment_adjustment_enabled
        self.sentiment_cache: dict[str, float] = {}  # symbol -> sentiment_score (-1.0 to 1.0)

    def generate_intents(
        self,
        universe: list[str],
        market_data: dict,
        candidate_map: dict[str, str] | None = None,
    ) -> list[PositionIntent]:
        """
        Generate position intents using weighted allocation.

        Process:
        1. Filter per_sector_weights to only active universe symbols
        2. Identify symbols in universe but not in config (positions from disabled sectors)
        3. Normalize weights globally (all tickers sum to 1.0)
        4. Generate intents with conviction = normalized_weight
        5. For unlisted symbols, generate exit intent (conviction=0)

        Args:
            universe: List of active symbols (from UniverseRegistry + existing positions)
            market_data: Dict of symbol -> {"price": float, ...}
            candidate_map: Optional symbol -> candidate_id mapping (unused)

        Returns:
            List of PositionIntent objects with:
                - target_quantity = 1 (fixed, allocator scales)
                - conviction = normalized_weight (allocator multiplies by budget)
                - reason = weight percentage description
                - For unlisted symbols: conviction=0 (forces exit)
        """
        # GUARDRAIL: Return empty if execution disabled
        if not self.execution_enabled:
            return []

        # Filter to active universe symbols
        active_symbols = set(universe)
        filtered_weights = self._filter_to_active_universe(active_symbols)

        # Identify symbols in universe but not in config (positions from disabled sectors)
        # These should be exited (conviction=0)
        configured_symbols = set()
        for sector_weights in self.per_sector_weights.values():
            configured_symbols.update(sector_weights.keys())
        unlisted_symbols = active_symbols - configured_symbols

        # Handle empty case (no active symbols)
        if not filtered_weights and not unlisted_symbols:
            return []

        # Normalize weights globally (all tickers sum to 1.0)
        normalized_weights = self._normalize_weights(filtered_weights)

        # Generate intents using conviction as weight encoding
        intents = []

        # Generate intents for configured symbols
        for symbol, weight in normalized_weights.items():
            # Skip symbols without price data
            if symbol not in market_data:
                continue

            price = market_data[symbol].get("price")
            if not price or price <= 0:
                continue

            # Create intent with conviction = normalized_weight
            intents.append(
                PositionIntent(
                    symbol=symbol,
                    target_quantity=1,  # Fixed (allocator scales by conviction)
                    conviction=weight,  # Weight as fraction (allocator multiplies by budget)
                    reason=f"AI Co-Pilot: {weight*100:.1f}% allocation",
                    candidate_id=None,
                )
            )

        # Generate exit intents for unlisted symbols (positions from disabled sectors)
        for symbol in unlisted_symbols:
            # Skip symbols without price data
            if symbol not in market_data:
                continue

            price = market_data[symbol].get("price")
            if not price or price <= 0:
                continue

            # Create exit intent (conviction=0 signals position reduction)
            intents.append(
                PositionIntent(
                    symbol=symbol,
                    target_quantity=1,  # Fixed (allocator scales by conviction)
                    conviction=0.0,  # Zero weight = exit signal
                    reason="AI Co-Pilot: Exit position from disabled sector",
                    candidate_id=None,
                )
            )

        return intents

    def _filter_to_active_universe(
        self, active_symbols: set[str]
    ) -> dict[str, dict[str, float]]:
        """
        Filter per_sector_weights to only symbols in active universe.

        This respects UniverseRegistry sector enables - if a sector is disabled,
        its tickers won't be in the universe and will be filtered out.

        Args:
            active_symbols: Set of symbols in current universe

        Returns:
            Nested dict of sector -> {ticker: weight} filtered to active symbols
        """
        filtered = {}
        for sector, ticker_weights in self.per_sector_weights.items():
            sector_filtered = {
                ticker: weight
                for ticker, weight in ticker_weights.items()
                if ticker in active_symbols
            }
            # Only include sector if it has at least one active symbol
            if sector_filtered:
                filtered[sector] = sector_filtered
        return filtered

    def update_sentiment_cache(self, sentiment_scores: dict[str, float]) -> None:
        """Update sentiment cache from runner.

        Args:
            sentiment_scores: Dict of symbol -> sentiment_score (-1.0 to 1.0)
        """
        self.sentiment_cache = sentiment_scores

    def _normalize_weights(
        self, filtered_weights: dict[str, dict[str, float]]
    ) -> dict[str, float]:
        """
        Flatten nested weights and normalize so sum = 1.0.

        If sentiment_adjustment_enabled, multiplies config weights by sentiment scores
        before normalization. This allows sentiment to dynamically adjust position sizes.

        This ensures full budget utilization by scaling all weights proportionally.

        Args:
            filtered_weights: Nested dict of sector -> {ticker: weight}

        Returns:
            Flat dict of ticker -> normalized_weight where sum(weights) = 1.0
        """
        # Flatten nested dict
        flat_weights = {}
        for sector, ticker_weights in filtered_weights.items():
            flat_weights.update(ticker_weights)

        # Apply sentiment adjustment if enabled
        if self.sentiment_adjustment_enabled and self.sentiment_cache:
            adjusted_weights = {}
            for ticker, weight in flat_weights.items():
                # Get sentiment score (default to 0.5 if not available)
                # Convert -1.0 to 1.0 range to 0.0 to 1.0 multiplier
                sentiment_score = self.sentiment_cache.get(ticker, 0.0)
                sentiment_multiplier = (sentiment_score + 1.0) / 2.0  # Map [-1, 1] to [0, 1]

                # Multiply config weight by sentiment
                adjusted_weights[ticker] = weight * sentiment_multiplier

            flat_weights = adjusted_weights

        # Normalize so sum = 1.0
        total_weight = sum(flat_weights.values())
        if total_weight == 0:
            return {}  # Avoid division by zero

        return {
            ticker: weight / total_weight for ticker, weight in flat_weights.items()
        }

    def __repr__(self) -> str:
        return (
            f"AICopilotWeightedStrategy("
            f"execution_enabled={self.execution_enabled}, "
            f"sectors={len(self.per_sector_weights)}, "
            f"tickers={sum(len(tw) for tw in self.per_sector_weights.values())}"
            f")"
        )
