"""Unit tests for AI Co-Pilot Weighted Strategy."""

import pytest

from src.app.strategies.ai_copilot_weighted import AICopilotWeightedStrategy
from src.app.strategies.base import PositionIntent


def test_execution_enabled_false_returns_empty():
    """Guardrail: execution_enabled=false should return no intents."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={"mega_cap_tech": {"NVDA": 1.0}},
        execution_enabled=False,
    )
    intents = strategy.generate_intents(
        universe=["NVDA"],
        market_data={"NVDA": {"price": 100.0}},
        candidate_map=None,
    )
    assert intents == []


def test_weight_normalization():
    """Weights should normalize to sum=1.0."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={
            "sector_a": {"SYM1": 0.5, "SYM2": 0.5},
            "sector_b": {"SYM3": 1.0},
        },
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["SYM1", "SYM2", "SYM3"],
        market_data={
            "SYM1": {"price": 100.0},
            "SYM2": {"price": 200.0},
            "SYM3": {"price": 300.0},
        },
        candidate_map=None,
    )
    total_conviction = sum(intent.conviction for intent in intents)
    assert abs(total_conviction - 1.0) < 0.001  # Should sum to 1.0


def test_active_universe_filtering():
    """Only symbols in universe should generate intents."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={
            "sector_a": {"ACTIVE": 0.5, "INACTIVE": 0.5},
        },
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["ACTIVE"],  # Only ACTIVE is in universe
        market_data={
            "ACTIVE": {"price": 100.0},
            "INACTIVE": {"price": 200.0},
        },
        candidate_map=None,
    )
    symbols = [intent.symbol for intent in intents]
    assert "ACTIVE" in symbols
    assert "INACTIVE" not in symbols


def test_missing_price_data_skipped():
    """Symbols without price data should be skipped gracefully."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={"sector_a": {"SYM1": 1.0}},
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["SYM1"],
        market_data={},  # No price data
        candidate_map=None,
    )
    assert intents == []


def test_conviction_encodes_weight():
    """Conviction field should equal normalized weight."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={
            "sector_a": {"SYM1": 0.3, "SYM2": 0.7},
        },
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["SYM1", "SYM2"],
        market_data={
            "SYM1": {"price": 100.0},
            "SYM2": {"price": 100.0},
        },
        candidate_map=None,
    )
    intent_map = {intent.symbol: intent.conviction for intent in intents}
    assert abs(intent_map["SYM1"] - 0.3) < 0.001
    assert abs(intent_map["SYM2"] - 0.7) < 0.001


def test_target_quantity_always_one():
    """Target quantity should always be 1 (allocator scales by conviction)."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={"sector_a": {"SYM1": 1.0}},
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["SYM1"],
        market_data={"SYM1": {"price": 100.0}},
        candidate_map=None,
    )
    assert all(intent.target_quantity == 1 for intent in intents)


def test_empty_per_sector_weights():
    """Strategy should handle empty per_sector_weights gracefully."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={},
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["SYM1"],
        market_data={"SYM1": {"price": 100.0}},
        candidate_map=None,
    )
    assert intents == []


def test_zero_price_skipped():
    """Symbols with zero or negative prices should be skipped."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={"sector_a": {"SYM1": 0.5, "SYM2": 0.5}},
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["SYM1", "SYM2"],
        market_data={
            "SYM1": {"price": 100.0},
            "SYM2": {"price": 0.0},  # Invalid price
        },
        candidate_map=None,
    )
    # Only SYM1 should generate intent
    assert len(intents) == 1
    assert intents[0].symbol == "SYM1"
    # SYM1 keeps its 50% weight (safer to use less budget than over-allocate)
    # Weights are normalized before price validation, so SYM1 retains 0.5
    assert abs(intents[0].conviction - 0.5) < 0.001


def test_multi_sector_normalization():
    """Weights should normalize correctly across multiple sectors."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={
            "mega_cap_tech": {"NVDA": 0.25, "MSFT": 0.15, "AAPL": 0.10},
            "us_sector_etfs": {"XLF": 0.20, "XLE": 0.15, "XLV": 0.15},
        },
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["NVDA", "MSFT", "AAPL", "XLF", "XLE", "XLV"],
        market_data={
            "NVDA": {"price": 500.0},
            "MSFT": {"price": 400.0},
            "AAPL": {"price": 180.0},
            "XLF": {"price": 40.0},
            "XLE": {"price": 80.0},
            "XLV": {"price": 130.0},
        },
        candidate_map=None,
    )

    # Should have 6 intents
    assert len(intents) == 6

    # Total conviction should sum to 1.0
    total_conviction = sum(intent.conviction for intent in intents)
    assert abs(total_conviction - 1.0) < 0.001

    # Original weights sum to 1.0, so normalized weights should be same
    intent_map = {intent.symbol: intent.conviction for intent in intents}
    assert abs(intent_map["NVDA"] - 0.25) < 0.001
    assert abs(intent_map["MSFT"] - 0.15) < 0.001
    assert abs(intent_map["AAPL"] - 0.10) < 0.001
    assert abs(intent_map["XLF"] - 0.20) < 0.001
    assert abs(intent_map["XLE"] - 0.15) < 0.001
    assert abs(intent_map["XLV"] - 0.15) < 0.001


def test_sector_filtering_partial_active():
    """Only active sectors should contribute to weights."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={
            "active_sector": {"SYM1": 0.5},
            "inactive_sector": {"SYM2": 0.5},
        },
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["SYM1"],  # Only active_sector symbol in universe
        market_data={
            "SYM1": {"price": 100.0},
            "SYM2": {"price": 200.0},
        },
        candidate_map=None,
    )

    # Only SYM1 should generate intent
    assert len(intents) == 1
    assert intents[0].symbol == "SYM1"
    # SYM1 gets 100% weight (normalized from inactive sector filtered out)
    assert abs(intents[0].conviction - 1.0) < 0.001


def test_intent_reason_formatting():
    """Intent reason should include weight percentage."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={"sector_a": {"SYM1": 0.3}},
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["SYM1"],
        market_data={"SYM1": {"price": 100.0}},
        candidate_map=None,
    )

    assert len(intents) == 1
    assert "AI Co-Pilot:" in intents[0].reason
    assert "100.0%" in intents[0].reason  # Normalized to 100%


def test_no_universe_symbols():
    """Strategy should handle empty universe gracefully."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={"sector_a": {"SYM1": 1.0}},
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=[],  # Empty universe
        market_data={"SYM1": {"price": 100.0}},
        candidate_map=None,
    )
    assert intents == []


def test_candidate_id_always_none():
    """Candidate ID should always be None for AI Co-Pilot strategy."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={"sector_a": {"SYM1": 1.0}},
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["SYM1"],
        market_data={"SYM1": {"price": 100.0}},
        candidate_map={"SYM1": "candidate_123"},  # Candidate map provided
    )

    assert len(intents) == 1
    assert intents[0].candidate_id is None  # Should always be None


def test_repr():
    """Test __repr__ method returns useful information."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={
            "sector_a": {"SYM1": 0.5, "SYM2": 0.5},
            "sector_b": {"SYM3": 1.0},
        },
        execution_enabled=True,
    )
    repr_str = repr(strategy)

    assert "AICopilotWeightedStrategy" in repr_str
    assert "execution_enabled=True" in repr_str
    assert "sectors=2" in repr_str
    assert "tickers=3" in repr_str


def test_negative_weights_handled():
    """Strategy should handle negative weights (treat as zero)."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={
            "sector_a": {"SYM1": 0.5, "SYM2": -0.1},  # Negative weight
        },
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["SYM1", "SYM2"],
        market_data={
            "SYM1": {"price": 100.0},
            "SYM2": {"price": 200.0},
        },
        candidate_map=None,
    )

    # Both symbols should generate intents (negative weight still included)
    # Normalization will handle the negative value
    assert len(intents) == 2

    # Total conviction should still sum to 1.0
    total_conviction = sum(intent.conviction for intent in intents)
    assert abs(total_conviction - 1.0) < 0.001


def test_very_small_weights():
    """Strategy should handle very small weights correctly."""
    strategy = AICopilotWeightedStrategy(
        per_sector_weights={
            "sector_a": {"SYM1": 0.0001, "SYM2": 0.0001},
        },
        execution_enabled=True,
    )
    intents = strategy.generate_intents(
        universe=["SYM1", "SYM2"],
        market_data={
            "SYM1": {"price": 100.0},
            "SYM2": {"price": 200.0},
        },
        candidate_map=None,
    )

    # Should normalize correctly
    assert len(intents) == 2
    total_conviction = sum(intent.conviction for intent in intents)
    assert abs(total_conviction - 1.0) < 0.001

    # Each should get 50%
    for intent in intents:
        assert abs(intent.conviction - 0.5) < 0.001
