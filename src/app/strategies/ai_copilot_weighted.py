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
    ):
        """
        Initialize AI Co-Pilot Weighted Strategy.

        Args:
            per_sector_weights: Nested dict of sector -> {ticker: weight}
                Example: {"mega_cap_tech": {"NVDA": 0.25, "MSFT": 0.15}}
            execution_enabled: Safety guardrail - must be true to trade
            rebalance_threshold_pct: Reserved for phase 2 (smart rebalancing)
            allow_shorts: Reserved for phase 2 (short positions)
        """
        super().__init__(name="AI_COPILOT_WEIGHTED")
        self.per_sector_weights = per_sector_weights or {}
        self.execution_enabled = execution_enabled
        self.rebalance_threshold_pct = rebalance_threshold_pct
        self.allow_shorts = allow_shorts

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
        2. Normalize weights globally (all tickers sum to 1.0)
        3. Generate intents with conviction = normalized_weight

        Args:
            universe: List of active symbols (from UniverseRegistry)
            market_data: Dict of symbol -> {"price": float, ...}
            candidate_map: Optional symbol -> candidate_id mapping (unused)

        Returns:
            List of PositionIntent objects with:
                - target_quantity = 1 (fixed, allocator scales)
                - conviction = normalized_weight (allocator multiplies by budget)
                - reason = weight percentage description
        """
        # GUARDRAIL: Return empty if execution disabled
        if not self.execution_enabled:
            return []

        # Filter to active universe symbols
        active_symbols = set(universe)
        filtered_weights = self._filter_to_active_universe(active_symbols)

        # Handle empty case (no active symbols)
        if not filtered_weights:
            return []

        # Normalize weights globally (all tickers sum to 1.0)
        normalized_weights = self._normalize_weights(filtered_weights)

        # Generate intents using conviction as weight encoding
        intents = []
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

    def _normalize_weights(
        self, filtered_weights: dict[str, dict[str, float]]
    ) -> dict[str, float]:
        """
        Flatten nested weights and normalize so sum = 1.0.

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
