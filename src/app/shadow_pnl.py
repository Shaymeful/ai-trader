"""Shadow PnL performance tracking without fills.

This module computes mark-to-market returns from hourly price changes
and attributes them to strategies based on notional exposure.
"""

import logging
from decimal import Decimal

from .strategies import PositionIntent


class ShadowPnLCalculator:
    """
    Calculate shadow PnL from market returns without requiring fills.

    Shadow PnL enables performance tracking in shadow mode and dry-run mode
    by computing mark-to-market returns based on price changes and attributing
    them to strategies based on their notional exposure.
    """

    def __init__(self, min_samples: int = 20):
        """
        Initialize shadow PnL calculator.

        Args:
            min_samples: Minimum samples required before weight updates (default 20)
        """
        self.min_samples = min_samples
        self.prev_prices: dict[str, float] = {}
        self.logger = logging.getLogger("ai-trader")

    def compute_symbol_returns(
        self, market_data: dict[str, dict], symbols: list[str]
    ) -> dict[str, float]:
        """
        Compute 1-period returns for each symbol using hourly close series.

        Return calculation: r = (close[-1] - close[-2]) / close[-2]

        Uses the closes array from hourly bars data. If closes array has < 2 elements,
        skips the symbol with a warning.

        Args:
            market_data: Dict mapping symbol -> {"price": float, "closes": list[float], ...}
            symbols: List of symbols to compute returns for

        Returns:
            Dict mapping symbol -> return (or empty if insufficient data)
        """
        symbol_returns = {}

        for symbol in symbols:
            if symbol not in market_data:
                self.logger.warning(f"{symbol}: No market data available, skipping return calculation")
                continue

            # Get closes array if available
            closes = market_data[symbol].get("closes", [])

            if len(closes) < 2:
                self.logger.warning(
                    f"{symbol}: Insufficient bars ({len(closes)}) for return calculation (need >= 2)"
                )
                continue

            # Compute 1-period return using last two closes
            close_prev = closes[-2]
            close_curr = closes[-1]

            if close_prev > 0:
                ret = (close_curr - close_prev) / close_prev
                symbol_returns[symbol] = ret
                self.logger.debug(
                    f"{symbol}: return={ret:.4f} (close[-2]={close_prev:.2f}, close[-1]={close_curr:.2f})"
                )
            else:
                self.logger.warning(f"{symbol}: Previous close is zero, skipping return calculation")

        if not symbol_returns:
            self.logger.info(
                "No returns computed this run (insufficient bar data)"
            )

        return symbol_returns

    def compute_strategy_notional_exposure(
        self,
        strategy_intents: dict[str, list[PositionIntent]],
        strategy_budgets: dict[str, Decimal],
        current_prices: dict[str, Decimal],
    ) -> dict[str, dict[str, float]]:
        """
        Allocate per-strategy notional exposure based on intents and budgets.

        Uses simple equal allocation: each symbol with target_qty > 0 gets
        an equal slice of the strategy's budget.

        Args:
            strategy_intents: Dict mapping strategy_name -> list of PositionIntent
            strategy_budgets: Dict mapping strategy_name -> allocated budget
            current_prices: Dict mapping symbol -> current price

        Returns:
            Dict[strategy_name][symbol] = notional_allocated
        """
        strategy_notionals: dict[str, dict[str, float]] = {}

        for strategy_name, intents in strategy_intents.items():
            budget = float(strategy_budgets.get(strategy_name, Decimal("0")))

            if budget <= 0:
                self.logger.warning(f"{strategy_name}: Zero or negative budget, skipping")
                strategy_notionals[strategy_name] = {}
                continue

            # Filter intents with positive target quantity
            intents_with_target = [i for i in intents if i.target_quantity > 0]

            if not intents_with_target:
                self.logger.debug(f"{strategy_name}: No intents with positive target_qty")
                strategy_notionals[strategy_name] = {}
                continue

            # Simple equal allocation across symbols
            num_symbols = len(intents_with_target)
            notional_per_symbol = budget / num_symbols

            strategy_notionals[strategy_name] = {}
            for intent in intents_with_target:
                symbol = intent.symbol
                strategy_notionals[strategy_name][symbol] = notional_per_symbol

                self.logger.debug(
                    f"{strategy_name}/{symbol}: allocated ${notional_per_symbol:.2f} "
                    f"(budget=${budget:.2f}, {num_symbols} symbols)"
                )

        return strategy_notionals

    def update_strategy_performance(
        self,
        strategy_states: dict,
        strategy_notionals: dict[str, dict[str, float]],
        symbol_returns: dict[str, float],
    ):
        """
        Update strategy performance based on attributed returns.

        For each strategy:
        - Compute weighted return = sum(notional[sym] * return[sym]) / total_notional
        - Update rolling_returns (append return)
        - Update cumulative_pnl
        - Increment trade_count (sample count)
        - Update drawdown

        Args:
            strategy_states: Dict of StrategyState objects to update
            strategy_notionals: Dict[strategy_name][symbol] = notional
            symbol_returns: Dict[symbol] = return
        """
        for strategy_name, notionals in strategy_notionals.items():
            if strategy_name not in strategy_states:
                self.logger.warning(f"{strategy_name}: Not in strategy_states, skipping")
                continue

            state = strategy_states[strategy_name]

            # Compute total notional
            total_notional = sum(notionals.values())

            if total_notional <= 0:
                self.logger.debug(f"{strategy_name}: Zero notional, skipping performance update")
                continue

            # Compute weighted return
            weighted_return = 0.0
            for symbol, notional in notionals.items():
                if symbol in symbol_returns:
                    weight = notional / total_notional
                    weighted_return += symbol_returns[symbol] * weight
                else:
                    self.logger.debug(
                        f"{strategy_name}/{symbol}: No return available, assuming 0.0"
                    )

            # Update state
            state.rolling_returns.append(weighted_return)

            # Trim to max_samples if needed (default 200)
            if len(state.rolling_returns) > 200:
                state.rolling_returns = state.rolling_returns[-200:]

            # Update cumulative PnL
            period_pnl = weighted_return * total_notional
            state.cumulative_pnl += period_pnl

            # Increment trade count (sample count)
            state.trade_count += 1

            # Update drawdown
            self._update_drawdown(state)

            # Update timestamp
            from datetime import UTC, datetime

            state.last_updated = datetime.now(UTC).isoformat()

            self.logger.info(
                f"{strategy_name}: return={weighted_return:.4f}, pnl=${period_pnl:.2f}, "
                f"cumul_pnl=${state.cumulative_pnl:.2f}, samples={state.trade_count}, "
                f"drawdown={state.drawdown:.4f}"
            )

    def _update_drawdown(self, state):
        """
        Update drawdown based on equity curve from rolling returns.

        Drawdown = (current_equity - peak_equity) / peak_equity

        Args:
            state: StrategyState object to update
        """
        if not state.rolling_returns:
            state.drawdown = 0.0
            return

        # Compute equity curve (starting at 1.0, multiply by (1 + return) each period)
        equity = 1.0
        peak_equity = 1.0
        max_drawdown = 0.0

        for ret in state.rolling_returns:
            equity *= 1.0 + ret
            peak_equity = max(peak_equity, equity)

            if peak_equity > 0:
                drawdown = (equity - peak_equity) / peak_equity
                max_drawdown = min(max_drawdown, drawdown)

        state.drawdown = max_drawdown
