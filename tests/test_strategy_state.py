"""Tests for strategy state management and performance tracking."""

import tempfile
from pathlib import Path

from src.app.performance import PerformanceTracker, update_strategy_weights
from src.app.state import (
    StrategyState,
    initialize_strategy_states,
    load_strategy_state,
    save_strategy_state,
)


def test_strategy_state_add_return():
    """Test adding returns to strategy state."""
    state = StrategyState(name="test")

    assert len(state.rolling_returns) == 0

    state.add_return(0.01)
    assert len(state.rolling_returns) == 1
    assert state.rolling_returns[0] == 0.01

    state.add_return(0.02)
    assert len(state.rolling_returns) == 2


def test_strategy_state_rolling_window():
    """Test that rolling returns window is limited."""
    state = StrategyState(name="test")

    # Add 250 returns
    for _ in range(250):
        state.add_return(0.001)

    # Should be limited to 200 (default max_samples)
    assert len(state.rolling_returns) == 200


def test_strategy_state_drawdown():
    """Test drawdown calculation."""
    state = StrategyState(name="test")

    # Add positive returns then negative
    state.add_return(0.10)  # Up 10%
    state.add_return(0.05)  # Up 5% more
    state.add_return(-0.10)  # Down 10%

    state.update_drawdown()

    # Drawdown should be negative (from peak to trough)
    assert state.drawdown < 0


def test_strategy_state_persistence():
    """Test saving and loading strategy state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)

        # Create states
        states = {
            "strategy1": StrategyState(name="strategy1", weight=0.6, cumulative_pnl=100.0),
            "strategy2": StrategyState(name="strategy2", weight=0.4, cumulative_pnl=-50.0),
        }

        # Add some returns
        states["strategy1"].add_return(0.01)
        states["strategy1"].add_return(0.02)
        states["strategy2"].add_return(-0.01)

        # Save
        save_strategy_state(states, state_dir)

        # Load
        loaded_states = load_strategy_state(state_dir)

        assert len(loaded_states) == 2
        assert "strategy1" in loaded_states
        assert "strategy2" in loaded_states

        assert loaded_states["strategy1"].weight == 0.6
        assert loaded_states["strategy1"].cumulative_pnl == 100.0
        assert len(loaded_states["strategy1"].rolling_returns) == 2

        assert loaded_states["strategy2"].weight == 0.4
        assert loaded_states["strategy2"].cumulative_pnl == -50.0


def test_initialize_strategy_states():
    """Test initializing strategies with equal weights."""
    states = {}
    strategy_names = ["strat1", "strat2", "strat3"]

    states = initialize_strategy_states(states, strategy_names)

    assert len(states) == 3
    expected_weight = 1.0 / 3.0

    for name in strategy_names:
        assert name in states
        assert abs(states[name].weight - expected_weight) < 1e-6


def test_update_strategy_weights_min_samples():
    """Test that weights don't change without minimum samples."""
    states = {
        "strat1": StrategyState(name="strat1", weight=0.5),
        "strat2": StrategyState(name="strat2", weight=0.5),
    }

    # Add only 10 samples (less than min_samples=20)
    for _ in range(10):
        states["strat1"].add_return(0.01)
        states["strat2"].add_return(-0.01)

    states["strat1"].update_drawdown()
    states["strat2"].update_drawdown()

    # Update weights
    updated_states = update_strategy_weights(states, min_samples=20)

    # Weights should remain roughly equal (scores both 1.0, equal starting weights)
    assert abs(updated_states["strat1"].weight - 0.5) < 0.1
    assert abs(updated_states["strat2"].weight - 0.5) < 0.1


def test_update_strategy_weights_with_samples():
    """Test weight updates with sufficient samples."""
    states = {
        "winner": StrategyState(name="winner", weight=0.5),
        "loser": StrategyState(name="loser", weight=0.5),
    }

    # Add 30 samples - winner has positive returns, loser negative
    for _ in range(30):
        states["winner"].add_return(0.02)  # Consistent 2% gains
        states["loser"].add_return(-0.01)  # Consistent 1% losses

    states["winner"].update_drawdown()
    states["loser"].update_drawdown()

    # Update weights
    updated_states = update_strategy_weights(states, min_samples=20)

    # Winner should get higher weight
    assert updated_states["winner"].weight > updated_states["loser"].weight

    # Weights should sum to 1.0
    total_weight = updated_states["winner"].weight + updated_states["loser"].weight
    assert abs(total_weight - 1.0) < 1e-6


def test_update_strategy_weights_bounds():
    """Test that weights respect min/max bounds."""
    states = {
        "great": StrategyState(name="great", weight=0.33),
        "good": StrategyState(name="good", weight=0.33),
        "bad": StrategyState(name="bad", weight=0.34),
    }

    # Add many samples with extreme differences
    for _ in range(100):
        states["great"].add_return(0.05)  # 5% per period
        states["good"].add_return(0.01)  # 1% per period
        states["bad"].add_return(-0.05)  # -5% per period

    for state in states.values():
        state.update_drawdown()

    # Update weights multiple times to let them settle
    for _ in range(20):
        updated_states = update_strategy_weights(
            states,
            min_samples=20,
            min_weight=0.05,
            max_weight=0.80,
            smoothing=0.5,  # Faster convergence for testing
        )

    # All weights should respect bounds
    for name, state in updated_states.items():
        assert state.weight >= 0.05, f"{name} weight {state.weight} below min"
        assert state.weight <= 0.80, f"{name} weight {state.weight} above max"

    # Weights should sum to 1.0
    total_weight = sum(state.weight for state in updated_states.values())
    assert abs(total_weight - 1.0) < 1e-6


def test_update_strategy_weights_drawdown_threshold():
    """Test that excessive drawdown clamps weight."""
    states = {
        "stable": StrategyState(name="stable", weight=0.5),
        "volatile": StrategyState(name="volatile", weight=0.5),
    }

    # Stable: consistent small gains
    for _ in range(30):
        states["stable"].add_return(0.01)

    # Volatile: big gain then big loss (causing drawdown)
    states["volatile"].add_return(0.20)  # +20%
    for _ in range(29):
        states["volatile"].add_return(-0.05)  # -5% each

    states["stable"].update_drawdown()
    states["volatile"].update_drawdown()

    # Volatile should have significant drawdown
    assert states["volatile"].drawdown < -0.02  # More than 2% drawdown

    # Update weights with drawdown threshold
    updated_states = update_strategy_weights(
        states, min_samples=20, drawdown_threshold=-0.02, smoothing=0.5
    )

    # Stable should get more weight due to volatile's drawdown
    assert updated_states["stable"].weight > updated_states["volatile"].weight


def test_performance_tracker():
    """Test performance tracker attribution."""
    tracker = PerformanceTracker()

    states = {
        "strat1": StrategyState(name="strat1", weight=0.5),
        "strat2": StrategyState(name="strat2", weight=0.5),
    }

    # Strategy allocations: each strategy holds different symbols
    strategy_allocations = {
        "strat1": {"AAPL": 1000.0},  # $1000 in AAPL
        "strat2": {"MSFT": 1000.0},  # $1000 in MSFT
    }

    # Prices
    from decimal import Decimal

    prev_prices = {"AAPL": Decimal("100.00"), "MSFT": Decimal("200.00")}
    current_prices = {"AAPL": Decimal("102.00"), "MSFT": Decimal("198.00")}

    # Update performance
    tracker.update_strategy_performance(states, strategy_allocations, current_prices, prev_prices)

    # AAPL: +2% return, strat1 should gain
    # MSFT: -1% return, strat2 should lose
    assert len(states["strat1"].rolling_returns) == 1
    assert len(states["strat2"].rolling_returns) == 1

    assert states["strat1"].rolling_returns[0] > 0  # Positive return
    assert states["strat2"].rolling_returns[0] < 0  # Negative return

    # Check cumulative PnL
    # AAPL: $1000 * 0.02 = $20 gain
    # MSFT: $1000 * -0.01 = -$10 loss
    assert abs(states["strat1"].cumulative_pnl - 20.0) < 1.0
    assert abs(states["strat2"].cumulative_pnl - (-10.0)) < 1.0
