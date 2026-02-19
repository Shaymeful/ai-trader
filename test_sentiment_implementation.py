"""Quick validation script for sentiment scoring implementation."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_sentiment_scorer_instantiation():
    """Test that SentimentScorer can be instantiated."""
    print("Testing SentimentScorer instantiation...")
    from src.app.selector.sentiment_scorer import SentimentScorer

    # Test without alpaca_client (should work)
    scorer = SentimentScorer(alpaca_client=None)
    print(f"  [OK] SentimentScorer created with weights: RSS={scorer.rss_weight}, Momentum={scorer.momentum_weight}, Volume={scorer.volume_weight}")

    # Test sentiment scoring without market data
    symbol = "AAPL"
    text = "Apple beats earnings expectations with strong iPhone sales"
    rss_confidence = 0.75

    combined, factors = scorer.compute_sentiment_score(symbol, text, rss_confidence)
    print(f"  [OK] Sentiment score computed: combined={combined:.4f}")
    print(f"    Factors: {factors}")

    assert -1.0 <= combined <= 1.0, "Combined score should be in [-1.0, 1.0]"
    assert "combined" in factors
    assert "rss" in factors
    assert "momentum" in factors
    assert "volume" in factors
    print("  [OK] All assertions passed")


def test_candidate_schema():
    """Test that Candidate schema accepts sentiment_factors."""
    print("\nTesting Candidate schema with sentiment_factors...")
    from src.app.candidates.schema import Candidate

    candidate = Candidate(
        candidate_id="test-123",
        created_at="2026-02-18T10:00:00",
        expires_at="2026-02-18T14:00:00",
        symbol="AAPL",
        action="buy",
        confidence=0.75,
        horizon="swing",
        sector="automation",
        event_type="rss_headline",
        tags=["test"],
        reason="Test candidate",
        sentiment_factors={
            "combined": 0.65,
            "rss": 0.5,
            "momentum": 0.7,
            "volume": 0.6,
        },
    )

    print(f"  [OK] Candidate created with sentiment_factors: {candidate.sentiment_factors}")
    assert candidate.sentiment_factors is not None
    assert candidate.sentiment_factors["combined"] == 0.65
    print("  [OK] All assertions passed")


def test_ai_copilot_sentiment_adjustment():
    """Test that AICopilotWeightedStrategy accepts sentiment parameters."""
    print("\nTesting AICopilotWeightedStrategy with sentiment adjustment...")
    from src.app.strategies.ai_copilot_weighted import AICopilotWeightedStrategy

    strategy = AICopilotWeightedStrategy(
        per_sector_weights={
            "automation": {"ARRY": 0.10, "FROG": 0.08},
            "energy": {"FSLR": 0.12, "ENPH": 0.10},
        },
        execution_enabled=True,
        sentiment_adjustment_enabled=True,
    )

    print(f"  [OK] Strategy created with sentiment_adjustment_enabled={strategy.sentiment_adjustment_enabled}")

    # Test sentiment cache update
    sentiment_cache = {
        "ARRY": 0.8,  # High sentiment
        "FROG": 0.2,  # Low sentiment
        "FSLR": 0.6,  # Moderate sentiment
        "ENPH": 0.7,  # Good sentiment
    }

    strategy.update_sentiment_cache(sentiment_cache)
    print(f"  [OK] Sentiment cache updated with {len(strategy.sentiment_cache)} symbols")

    # Test weight normalization with sentiment adjustment
    filtered_weights = {
        "automation": {"ARRY": 0.10, "FROG": 0.08},
        "energy": {"FSLR": 0.12, "ENPH": 0.10},
    }

    normalized = strategy._normalize_weights(filtered_weights)
    print(f"  [OK] Normalized weights with sentiment adjustment:")
    for symbol, weight in normalized.items():
        print(f"    {symbol}: {weight:.4f} (sentiment: {sentiment_cache.get(symbol, 0.0):.2f})")

    # Verify that weights sum to 1.0
    total = sum(normalized.values())
    assert abs(total - 1.0) < 0.001, f"Weights should sum to 1.0, got {total}"
    print("  [OK] All assertions passed")


def test_exit_advisor_thresholds():
    """Test that ExitAdvisor accepts hard threshold parameters."""
    print("\nTesting ExitAdvisor with hard thresholds...")
    from src.app.exit_advisor import ExitAdvisor

    # Create a mock sell scanner (just for instantiation test)
    class MockSellScanner:
        def __init__(self):
            self.llm_provider = None

    sell_scanner = MockSellScanner()

    exit_advisor = ExitAdvisor(
        sell_scanner=sell_scanner,
        cooldown_hours=4,
        stop_loss_pct=6.0,
        take_profit_pct=10.0,
        trailing_stop_trigger_pct=5.0,
        trailing_stop_pct=3.0,
    )

    print(f"  [OK] ExitAdvisor created with thresholds:")
    print(f"    Stop loss: {exit_advisor.stop_loss_pct}%")
    print(f"    Take profit: {exit_advisor.take_profit_pct}%")
    print(f"    Trailing trigger: {exit_advisor.trailing_stop_trigger_pct}%")
    print(f"    Trailing stop: {exit_advisor.trailing_stop_pct}%")

    # Test hard threshold checking
    symbol = "AAPL"
    current_price = 94.0  # -6% from entry
    avg_entry_price = 100.0
    market_regime = "neutral"

    exit_candidate = exit_advisor._check_hard_thresholds(
        symbol=symbol,
        current_price=current_price,
        avg_entry_price=avg_entry_price,
        market_regime=market_regime,
    )

    assert exit_candidate is not None, "Stop loss should trigger at -6%"
    print(f"  [OK] Stop loss triggered: {exit_candidate.reason}")
    print("  [OK] All assertions passed")


def test_mode_profile_loading():
    """Test that the new mode profile can be loaded."""
    print("\nTesting mode profile loading...")
    from src.app.config import load_mode_profiles

    modes = load_mode_profiles()
    assert "aggressive_small_mid_sentiment" in modes["profiles"], "New mode profile should be present"
    print("  [OK] Mode profile 'aggressive_small_mid_sentiment' loaded successfully")

    profile = modes["profiles"]["aggressive_small_mid_sentiment"]
    assert "strategies" in profile
    assert "universe" in profile
    assert "selector" in profile
    assert "execution_gate" in profile
    assert "exit_thresholds" in profile
    print("  [OK] Profile contains all required sections")

    # Check exit thresholds
    thresholds = profile["exit_thresholds"]
    print(f"  Exit thresholds: {thresholds}")
    assert thresholds["stop_loss_pct"] == 6.0
    assert thresholds["take_profit_pct"] == 10.0
    print("  [OK] All assertions passed")


if __name__ == "__main__":
    print("=" * 80)
    print("Sentiment Implementation Validation")
    print("=" * 80)

    try:
        test_sentiment_scorer_instantiation()
        test_candidate_schema()
        test_ai_copilot_sentiment_adjustment()
        test_exit_advisor_thresholds()
        test_mode_profile_loading()

        print("\n" + "=" * 80)
        print("[SUCCESS] All validation tests passed!")
        print("=" * 80)

    except Exception as e:
        print(f"\n[FAILED] Validation failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
