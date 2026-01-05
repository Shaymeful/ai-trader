"""Tests for equity-based allocation and sizing engine."""

from decimal import Decimal

from src.app import allocation
from src.app.strategies.base import PositionIntent


class TestGetTotalEquity:
    """Tests for get_total_equity function."""

    def test_get_equity_from_account_state(self):
        """Test extracting equity from account state dict."""
        account_state = {"equity": "50000.00", "buying_power": "100000.00"}
        equity = allocation.get_total_equity(account_state)
        assert equity == 50000.0

    def test_get_equity_with_numeric_value(self):
        """Test with numeric equity value (not string)."""
        account_state = {"equity": 75000.50}
        equity = allocation.get_total_equity(account_state)
        assert equity == 75000.50

    def test_get_equity_none_account_state(self):
        """Test with None account state."""
        equity = allocation.get_total_equity(None)
        assert equity is None

    def test_get_equity_missing_field(self):
        """Test with account state missing equity field."""
        account_state = {"buying_power": "100000.00"}
        equity = allocation.get_total_equity(account_state)
        assert equity is None

    def test_get_equity_invalid_value(self):
        """Test with invalid equity value."""
        account_state = {"equity": "not-a-number"}
        equity = allocation.get_total_equity(account_state)
        assert equity is None


class TestComputeWeightSummary:
    """Tests for compute_weight_summary function."""

    def test_normalize_weights_basic(self):
        """Test basic weight normalization."""
        from src.app.strategy_registry import StrategyConfig

        strategies = [
            StrategyConfig(
                strategy_id="A",
                name="Strategy A",
                description="",
                enabled=True,
                weight=0.5,
                params={},
                risk_limits={},
            ),
            StrategyConfig(
                strategy_id="B",
                name="Strategy B",
                description="",
                enabled=True,
                weight=0.3,
                params={},
                risk_limits={},
            ),
            StrategyConfig(
                strategy_id="C",
                name="Strategy C",
                description="",
                enabled=False,
                weight=0.2,
                params={},
                risk_limits={},
            ),
        ]

        result = allocation.compute_weight_summary(strategies)

        assert result["enabled_ids"] == ["A", "B"]
        assert result["sum_enabled_weights"] == 0.8
        assert abs(result["normalized_weights"]["A"] - 0.625) < 0.001  # 0.5 / 0.8
        assert abs(result["normalized_weights"]["B"] - 0.375) < 0.001  # 0.3 / 0.8
        assert result["configured_weights"]["A"] == 0.5
        assert result["configured_weights"]["B"] == 0.3
        assert result["configured_weights"]["C"] == 0.2

    def test_normalize_weights_sum_zero(self):
        """Test normalization when all enabled weights sum to zero."""
        from src.app.strategy_registry import StrategyConfig

        strategies = [
            StrategyConfig(
                strategy_id="A",
                name="Strategy A",
                description="",
                enabled=True,
                weight=0.0,
                params={},
                risk_limits={},
            ),
            StrategyConfig(
                strategy_id="B",
                name="Strategy B",
                description="",
                enabled=True,
                weight=0.0,
                params={},
                risk_limits={},
            ),
        ]

        result = allocation.compute_weight_summary(strategies)

        # Should assign equal weights when sum is zero
        assert result["enabled_ids"] == ["A", "B"]
        assert result["sum_enabled_weights"] == 0.0
        assert result["normalized_weights"]["A"] == 0.5
        assert result["normalized_weights"]["B"] == 0.5

    def test_no_enabled_strategies(self):
        """Test with no enabled strategies."""
        from src.app.strategy_registry import StrategyConfig

        strategies = [
            StrategyConfig(
                strategy_id="A",
                name="Strategy A",
                description="",
                enabled=False,
                weight=0.5,
                params={},
                risk_limits={},
            ),
        ]

        result = allocation.compute_weight_summary(strategies)

        assert result["enabled_ids"] == []
        assert result["sum_enabled_weights"] == 0.0
        assert result["normalized_weights"] == {}


class TestComputeStrategyBudget:
    """Tests for compute_strategy_budget function."""

    def test_compute_budget_basic(self):
        """Test basic budget computation."""
        equity = 50000.0
        normalized_weight = 0.625
        budget = allocation.compute_strategy_budget(equity, normalized_weight)
        assert abs(budget - 31250.0) < 0.01  # 50000 * 0.625

    def test_compute_budget_negative_equity(self):
        """Test with negative equity (should clamp to zero)."""
        equity = -1000.0
        normalized_weight = 0.5
        budget = allocation.compute_strategy_budget(equity, normalized_weight)
        assert budget == 0.0

    def test_compute_budget_weight_out_of_range(self):
        """Test with weight outside [0,1] range (should clamp)."""
        equity = 50000.0

        # Weight > 1.0
        budget = allocation.compute_strategy_budget(equity, 1.5)
        assert abs(budget - 50000.0) < 0.01  # Clamped to 1.0

        # Weight < 0.0
        budget = allocation.compute_strategy_budget(equity, -0.5)
        assert budget == 0.0  # Clamped to 0.0


class TestComputeTargetNotional:
    """Tests for compute_target_notional function."""

    def test_compute_notional_basic(self):
        """Test basic notional computation."""
        budget = 31250.0
        conviction = 0.85
        notional = allocation.compute_target_notional(budget, conviction)
        assert abs(notional - 26562.5) < 0.01  # 31250 * 0.85

    def test_compute_notional_with_risk_limit(self):
        """Test notional capped by max_position_size."""
        budget = 31250.0
        conviction = 0.85
        risk_limits = {"max_position_size": 5000.0}

        notional = allocation.compute_target_notional(budget, conviction, risk_limits)
        assert notional == 5000.0  # Capped to max_position_size

    def test_compute_notional_conviction_out_of_range(self):
        """Test with conviction outside [0,1] range (should clamp)."""
        budget = 10000.0

        # Conviction > 1.0
        notional = allocation.compute_target_notional(budget, 1.5)
        assert notional == 10000.0  # Clamped to 1.0

        # Conviction < 0.0
        notional = allocation.compute_target_notional(budget, -0.5)
        assert notional == 0.0  # Clamped to 0.0


class TestComputeQtyFromNotional:
    """Tests for compute_qty_from_notional function."""

    def test_qty_fractional_allowed(self):
        """Test quantity computation with fractional shares allowed."""
        price = 150.0
        notional = 5000.0
        qty = allocation.compute_qty_from_notional(price, notional, allow_fractional=True)
        assert abs(qty - 33.333333) < 0.001  # 5000 / 150

    def test_qty_fractional_not_allowed(self):
        """Test quantity computation with whole shares only."""
        price = 150.0
        notional = 5000.0
        qty = allocation.compute_qty_from_notional(price, notional, allow_fractional=False)
        assert qty == 33  # Floor to whole shares

    def test_qty_with_decimal_price(self):
        """Test with Decimal price."""
        price = Decimal("150.50")
        notional = 5000.0
        qty = allocation.compute_qty_from_notional(price, notional, allow_fractional=True)
        assert abs(qty - 33.22259) < 0.001

    def test_qty_invalid_price(self):
        """Test with invalid (zero or negative) price."""
        notional = 5000.0

        qty = allocation.compute_qty_from_notional(0.0, notional, allow_fractional=True)
        assert qty == 0

        qty = allocation.compute_qty_from_notional(-100.0, notional, allow_fractional=True)
        assert qty == 0

    def test_qty_negative_notional(self):
        """Test with negative notional (should use 0)."""
        price = 150.0
        notional = -1000.0
        qty = allocation.compute_qty_from_notional(price, notional, allow_fractional=True)
        assert qty == 0.0

    def test_qty_min_qty_enforcement(self):
        """Test min_qty parameter enforcement."""
        price = 1000.0
        notional = 500.0  # Would result in 0 shares

        # With allow_fractional=False, should respect min_qty
        qty = allocation.compute_qty_from_notional(
            price, notional, allow_fractional=False, min_qty=1
        )
        assert qty == 1


class TestNetIntentsBySymbol:
    """Tests for net_intents_by_symbol function."""

    def test_net_single_symbol_multiple_intents(self):
        """Test netting multiple intents for same symbol."""
        intents = [
            PositionIntent("AAPL", 10, 0.8, "Strong momentum"),
            PositionIntent("AAPL", -5, 0.6, "Risk reduction"),
        ]
        market_data = {"AAPL": {"price": 150.0}}

        result = allocation.net_intents_by_symbol(intents, market_data)

        assert "AAPL" in result
        assert result["AAPL"]["net_notional"] == 750.0  # (10 * 150) + (-5 * 150)
        assert result["AAPL"]["net_quantity"] == 5.0
        assert result["AAPL"]["final_direction"] == "buy"
        assert result["AAPL"]["price"] == 150.0

    def test_net_multiple_symbols(self):
        """Test netting intents for multiple symbols."""
        intents = [
            PositionIntent("AAPL", 10, 0.8, "Buy signal"),
            PositionIntent("SPY", -5, 0.7, "Sell signal"),
        ]
        market_data = {"AAPL": {"price": 150.0}, "SPY": {"price": 400.0}}

        result = allocation.net_intents_by_symbol(intents, market_data)

        assert len(result) == 2
        assert result["AAPL"]["net_notional"] == 1500.0  # 10 * 150
        assert result["AAPL"]["final_direction"] == "buy"
        assert result["SPY"]["net_notional"] == -2000.0  # -5 * 400
        assert result["SPY"]["final_direction"] == "sell"

    def test_net_canceling_intents(self):
        """Test intents that cancel out to neutral."""
        intents = [
            PositionIntent("AAPL", 10, 0.8, "Buy"),
            PositionIntent("AAPL", -10, 0.8, "Sell"),
        ]
        market_data = {"AAPL": {"price": 150.0}}

        result = allocation.net_intents_by_symbol(intents, market_data)

        assert result["AAPL"]["net_notional"] == 0.0
        assert result["AAPL"]["net_quantity"] == 0.0
        assert result["AAPL"]["final_direction"] == "neutral"

    def test_net_with_strategy_attribution(self):
        """Test that strategy attribution is tracked."""
        intent1 = PositionIntent("AAPL", 10, 0.8, "Buy")
        intent2 = PositionIntent("AAPL", -5, 0.6, "Sell")
        intents = [intent1, intent2]

        market_data = {"AAPL": {"price": 150.0}}

        # Test without strategy_map (it's optional)
        # Note: PositionIntent is not hashable so can't be used as dict key
        result = allocation.net_intents_by_symbol(intents, market_data, strategy_map=None)

        contributing = result["AAPL"]["contributing_intents"]
        assert len(contributing) == 2
        # Without strategy_map, strategy_id will be None
        assert contributing[0]["strategy_id"] is None
        assert contributing[0]["quantity"] == 10
        assert contributing[1]["strategy_id"] is None
        assert contributing[1]["quantity"] == -5

    def test_net_missing_price_data(self):
        """Test handling of missing market data."""
        intents = [
            PositionIntent("AAPL", 10, 0.8, "Buy"),
            PositionIntent("SPY", 5, 0.7, "Buy"),  # No price data for SPY
        ]
        market_data = {"AAPL": {"price": 150.0}}

        result = allocation.net_intents_by_symbol(intents, market_data)

        # AAPL should be included
        assert "AAPL" in result
        # SPY should be skipped (warning logged)
        assert "SPY" not in result

    def test_net_invalid_price(self):
        """Test handling of invalid price."""
        intents = [PositionIntent("AAPL", 10, 0.8, "Buy")]
        market_data = {"AAPL": {"price": None}}

        result = allocation.net_intents_by_symbol(intents, market_data)

        # Should skip AAPL due to invalid price
        assert "AAPL" not in result


class TestIntegrationScenarios:
    """Integration tests for complete allocation flows."""

    def test_full_allocation_flow(self):
        """Test complete allocation flow from equity to quantities."""
        # 1. Get equity
        account_state = {"equity": "50000.00"}
        equity = allocation.get_total_equity(account_state)
        assert equity == 50000.0

        # 2. Compute weights (simulated strategies)
        from src.app.strategy_registry import StrategyConfig

        strategies = [
            StrategyConfig(
                strategy_id="Trend",
                name="Trend",
                description="",
                enabled=True,
                weight=0.6,
                params={},
                risk_limits={"max_position_size": 5000.0},
            ),
            StrategyConfig(
                strategy_id="MeanReversion",
                name="MeanReversion",
                description="",
                enabled=True,
                weight=0.4,
                params={},
                risk_limits={"max_position_size": 3000.0},
            ),
        ]

        weight_summary = allocation.compute_weight_summary(strategies)
        assert weight_summary["normalized_weights"]["Trend"] == 0.6
        assert weight_summary["normalized_weights"]["MeanReversion"] == 0.4

        # 3. Compute budgets
        trend_budget = allocation.compute_strategy_budget(
            equity, weight_summary["normalized_weights"]["Trend"]
        )
        mr_budget = allocation.compute_strategy_budget(
            equity, weight_summary["normalized_weights"]["MeanReversion"]
        )

        assert trend_budget == 30000.0
        assert mr_budget == 20000.0

        # 4. Compute notionals from conviction
        trend_config = strategies[0]
        trend_notional = allocation.compute_target_notional(
            trend_budget, conviction=0.85, risk_limits=trend_config.risk_limits
        )
        assert trend_notional == 5000.0  # Capped by max_position_size

        mr_config = strategies[1]
        mr_notional = allocation.compute_target_notional(
            mr_budget, conviction=0.70, risk_limits=mr_config.risk_limits
        )
        assert mr_notional == 3000.0  # Capped by max_position_size

        # 5. Convert to quantities
        price = 150.0
        trend_qty = allocation.compute_qty_from_notional(
            price, trend_notional, allow_fractional=False
        )
        mr_qty = allocation.compute_qty_from_notional(price, mr_notional, allow_fractional=False)

        assert trend_qty == 33  # Floor(5000/150)
        assert mr_qty == 20  # Floor(3000/150)

    def test_allocation_with_disabled_strategy(self):
        """Test that disabled strategies don't affect normalization."""
        from src.app.strategy_registry import StrategyConfig

        strategies = [
            StrategyConfig(
                strategy_id="A",
                name="A",
                description="",
                enabled=True,
                weight=0.5,
                params={},
                risk_limits={},
            ),
            StrategyConfig(
                strategy_id="B",
                name="B",
                description="",
                enabled=False,
                weight=0.5,
                params={},
                risk_limits={},
            ),
        ]

        weight_summary = allocation.compute_weight_summary(strategies)

        # Only enabled strategy should get 100% allocation
        assert weight_summary["normalized_weights"]["A"] == 1.0
        assert "B" not in weight_summary["normalized_weights"]
