"""Tests for Shadow PnL performance tracking."""

import tempfile
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.app.shadow_pnl import ShadowPnLCalculator
from src.app.state import (
    StrategyState,
    initialize_strategy_states,
    load_strategy_state,
    save_strategy_state,
    update_strategy_weights,
)
from src.app.strategies import PositionIntent


def test_symbol_returns_calculation():
    """Test that symbol returns are calculated correctly using closes array."""
    calculator = ShadowPnLCalculator()

    # Market data with closes array
    market_data = {
        "SPY": {
            "price": 404.0,
            "ma": 395.0,
            "zscore": 0.5,
            "closes": [398.0, 400.0, 404.0],  # Last return: (404 - 400) / 400 = 0.01
        },
        "QQQ": {
            "price": 297.0,
            "ma": 295.0,
            "zscore": 0.3,
            "closes": [305.0, 300.0, 297.0],  # Last return: (297 - 300) / 300 = -0.01
        },
    }
    returns = calculator.compute_symbol_returns(market_data, ["SPY", "QQQ"])

    # Check returns
    assert "SPY" in returns
    assert "QQQ" in returns
    assert returns["SPY"] == pytest.approx(0.01, abs=1e-6)  # (404 - 400) / 400 = 0.01
    assert returns["QQQ"] == pytest.approx(-0.01, abs=1e-6)  # (297 - 300) / 300 = -0.01


def test_symbol_returns_first_run_no_previous():
    """Test that insufficient bars returns empty dict."""
    calculator = ShadowPnLCalculator()

    market_data = {
        "SPY": {"price": 400.0, "ma": 395.0, "zscore": 0.5, "closes": [400.0]},  # Only 1 bar
    }
    returns = calculator.compute_symbol_returns(market_data, ["SPY"])

    assert returns == {}  # Insufficient data (need >= 2 bars)


def test_notional_exposure_equal_allocation():
    """Test that notional is allocated equally across intents."""
    calculator = ShadowPnLCalculator()

    strategy_intents = {
        "Trend": [
            PositionIntent("SPY", 1, 0.5, "Buy signal"),
            PositionIntent("QQQ", 1, 0.3, "Buy signal"),
        ],
    }
    strategy_budgets = {"Trend": Decimal("5000")}
    current_prices = {"SPY": Decimal("400"), "QQQ": Decimal("300")}

    notionals = calculator.compute_strategy_notional_exposure(
        strategy_intents, strategy_budgets, current_prices
    )

    assert "Trend" in notionals
    assert "SPY" in notionals["Trend"]
    assert "QQQ" in notionals["Trend"]

    # Each symbol should get 5000 / 2 = 2500
    assert notionals["Trend"]["SPY"] == pytest.approx(2500.0, abs=1e-2)
    assert notionals["Trend"]["QQQ"] == pytest.approx(2500.0, abs=1e-2)


def test_notional_exposure_zero_target_qty_excluded():
    """Test that intents with target_qty=0 are excluded from allocation."""
    calculator = ShadowPnLCalculator()

    strategy_intents = {
        "Trend": [
            PositionIntent("SPY", 1, 0.5, "Buy signal"),
            PositionIntent("QQQ", 0, 0.0, "No signal"),  # target_qty=0
        ],
    }
    strategy_budgets = {"Trend": Decimal("5000")}
    current_prices = {"SPY": Decimal("400"), "QQQ": Decimal("300")}

    notionals = calculator.compute_strategy_notional_exposure(
        strategy_intents, strategy_budgets, current_prices
    )

    assert "Trend" in notionals
    assert "SPY" in notionals["Trend"]
    assert "QQQ" not in notionals["Trend"]  # QQQ excluded (target_qty=0)

    # SPY should get full budget
    assert notionals["Trend"]["SPY"] == pytest.approx(5000.0, abs=1e-2)


def test_strategy_performance_update():
    """Test that strategy performance is updated correctly."""
    calculator = ShadowPnLCalculator()

    # Create strategy state
    states = {
        "Trend": StrategyState(
            name="Trend",
            weight=1.0,
            cumulative_pnl=0.0,
            rolling_returns=[],
            drawdown=0.0,
            trade_count=0,
            last_updated="",
        )
    }

    # Set up notionals and returns
    strategy_notionals = {"Trend": {"SPY": 2500.0}}
    symbol_returns = {"SPY": 0.01}  # 1% return

    # Update performance
    calculator.update_strategy_performance(states, strategy_notionals, symbol_returns)

    # Check state updates
    assert len(states["Trend"].rolling_returns) == 1
    assert states["Trend"].rolling_returns[0] == pytest.approx(0.01, abs=1e-6)
    assert states["Trend"].cumulative_pnl == pytest.approx(25.0, abs=1e-2)  # 0.01 * 2500 = 25
    assert states["Trend"].trade_count == 1


def test_weight_gating_insufficient_samples():
    """Test that weights stay equal when samples < min_samples."""
    states = {
        "Trend": StrategyState(
            name="Trend",
            weight=0.5,
            cumulative_pnl=50.0,
            rolling_returns=[0.01] * 10,  # Only 10 samples (< 20)
            drawdown=0.0,
            trade_count=10,
            last_updated="",
        ),
        "MeanRev": StrategyState(
            name="MeanRev",
            weight=0.5,
            cumulative_pnl=10.0,
            rolling_returns=[0.001] * 10,  # Only 10 samples (< 20)
            drawdown=0.0,
            trade_count=10,
            last_updated="",
        ),
    }

    updated_states = update_strategy_weights(states, min_samples=20)

    # Weights should stay equal
    assert updated_states["Trend"].weight == pytest.approx(0.5, abs=1e-6)
    assert updated_states["MeanRev"].weight == pytest.approx(0.5, abs=1e-6)


def test_weight_update_sufficient_samples():
    """Test that weights update when samples >= min_samples."""
    states = {
        "Trend": StrategyState(
            name="Trend",
            weight=0.5,
            cumulative_pnl=100.0,
            rolling_returns=[0.01] * 25,  # 25 samples (>= 20), outperforming
            drawdown=-0.01,
            trade_count=25,
            last_updated="",
        ),
        "MeanRev": StrategyState(
            name="MeanRev",
            weight=0.5,
            cumulative_pnl=10.0,
            rolling_returns=[0.001] * 25,  # 25 samples (>= 20), underperforming
            drawdown=-0.02,
            trade_count=25,
            last_updated="",
        ),
    }

    updated_states = update_strategy_weights(states, min_samples=20)

    # Trend should have higher weight than MeanRev
    assert updated_states["Trend"].weight > 0.5
    assert updated_states["MeanRev"].weight < 0.5

    # Weights should sum to 1.0
    total_weight = updated_states["Trend"].weight + updated_states["MeanRev"].weight
    assert total_weight == pytest.approx(1.0, abs=1e-6)


def test_weight_bounds_enforcement():
    """Test that weights are clamped to [min_weight, max_weight]."""
    states = {
        "Trend": StrategyState(
            name="Trend",
            weight=0.5,
            cumulative_pnl=500.0,
            rolling_returns=[0.05] * 25,  # Very high returns
            drawdown=0.0,
            trade_count=25,
            last_updated="",
        ),
        "MeanRev": StrategyState(
            name="MeanRev",
            weight=0.5,
            cumulative_pnl=-200.0,
            rolling_returns=[-0.02] * 25,  # Negative returns
            drawdown=-0.15,
            trade_count=25,
            last_updated="",
        ),
    }

    updated_states = update_strategy_weights(
        states, min_samples=20, min_weight=0.05, max_weight=0.80
    )

    # Check bounds
    assert updated_states["Trend"].weight <= 0.80
    assert updated_states["MeanRev"].weight >= 0.05

    # Weights should sum to 1.0
    total_weight = updated_states["Trend"].weight + updated_states["MeanRev"].weight
    assert total_weight == pytest.approx(1.0, abs=1e-6)


def test_drawdown_calculation():
    """Test that drawdown is calculated correctly."""
    calculator = ShadowPnLCalculator()

    states = {
        "Trend": StrategyState(
            name="Trend",
            weight=1.0,
            cumulative_pnl=0.0,
            rolling_returns=[],
            drawdown=0.0,
            trade_count=0,
            last_updated="",
        )
    }

    # Simulate returns: +1%, -3%, +2%
    # Equity: 1.0 -> 1.01 -> 0.9797 -> 0.999194
    # Peak: 1.01, so max drawdown = (0.9797 - 1.01) / 1.01 = -0.03
    strategy_notionals = {"Trend": {"SPY": 1000.0}}
    symbol_returns_list = [
        {"SPY": 0.01},  # +1%
        {"SPY": -0.03},  # -3%
        {"SPY": 0.02},  # +2%
    ]

    for symbol_returns in symbol_returns_list:
        calculator.update_strategy_performance(states, strategy_notionals, symbol_returns)

    # Drawdown should be negative (max decline from peak)
    assert states["Trend"].drawdown < 0
    assert states["Trend"].drawdown == pytest.approx(-0.03, abs=1e-3)


def test_state_persistence():
    """Test that state is saved and loaded correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        states = {
            "Trend": StrategyState(
                name="Trend",
                weight=0.6,
                cumulative_pnl=50.0,
                rolling_returns=[0.01, 0.02, 0.005],
                drawdown=-0.01,
                trade_count=3,
                last_updated=datetime.now(UTC).isoformat(),
            ),
            "MeanRev": StrategyState(
                name="MeanRev",
                weight=0.4,
                cumulative_pnl=20.0,
                rolling_returns=[0.005, 0.01],
                drawdown=-0.005,
                trade_count=2,
                last_updated=datetime.now(UTC).isoformat(),
            ),
        }

        # Save state
        save_strategy_state(states, state_dir=tmpdir)

        # Load state
        loaded_states = load_strategy_state(state_dir=tmpdir)

        # Check all fields match
        assert "Trend" in loaded_states
        assert "MeanRev" in loaded_states

        assert loaded_states["Trend"].name == "Trend"
        assert loaded_states["Trend"].weight == pytest.approx(0.6, abs=1e-6)
        assert loaded_states["Trend"].cumulative_pnl == pytest.approx(50.0, abs=1e-6)
        assert len(loaded_states["Trend"].rolling_returns) == 3
        assert loaded_states["Trend"].trade_count == 3

        assert loaded_states["MeanRev"].name == "MeanRev"
        assert loaded_states["MeanRev"].weight == pytest.approx(0.4, abs=1e-6)
        assert loaded_states["MeanRev"].cumulative_pnl == pytest.approx(20.0, abs=1e-6)
        assert len(loaded_states["MeanRev"].rolling_returns) == 2
        assert loaded_states["MeanRev"].trade_count == 2


def test_initialize_strategy_states():
    """Test that strategy states are initialized with equal weights."""
    states = {}
    strategy_names = ["Trend_MA20", "MeanRev_Z1.0", "Momentum_RSI"]

    initialized_states = initialize_strategy_states(states, strategy_names)

    # Check that all strategies are initialized
    assert len(initialized_states) == 3
    for name in strategy_names:
        assert name in initialized_states

    # Check equal weights (1/3 each)
    equal_weight = 1.0 / 3
    for state in initialized_states.values():
        assert state.weight == pytest.approx(equal_weight, abs=1e-6)
        assert state.cumulative_pnl == 0.0
        assert len(state.rolling_returns) == 0
        assert state.trade_count == 0
