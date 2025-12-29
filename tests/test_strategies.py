"""Tests for trading strategies."""

from src.app.strategies import MeanReversionStrategy, PositionIntent, TrendStrategy


def test_trend_strategy_bullish_signal():
    """Test trend strategy generates long position when price > MA."""
    strategy = TrendStrategy(ma_period=20)

    market_data = {"SPY": {"price": 450.0, "ma": 440.0}}

    intents = strategy.generate_intents(["SPY"], market_data)

    assert len(intents) == 1
    assert intents[0].symbol == "SPY"
    assert intents[0].target_quantity == 1
    assert intents[0].conviction > 0
    assert ">" in intents[0].reason


def test_trend_strategy_bearish_signal():
    """Test trend strategy generates flat position when price <= MA."""
    strategy = TrendStrategy(ma_period=20)

    market_data = {"SPY": {"price": 440.0, "ma": 450.0}}

    intents = strategy.generate_intents(["SPY"], market_data)

    assert len(intents) == 1
    assert intents[0].symbol == "SPY"
    assert intents[0].target_quantity == 0
    assert intents[0].conviction == 0.0
    assert "<=" in intents[0].reason


def test_trend_strategy_skips_missing_data():
    """Test trend strategy skips symbols with missing data."""
    strategy = TrendStrategy(ma_period=20)

    market_data = {"SPY": {"price": 450.0}}  # Missing MA

    intents = strategy.generate_intents(["SPY", "QQQ"], market_data)

    # Should have no intents since SPY missing MA and QQQ not in data
    assert len(intents) == 0


def test_mean_reversion_oversold_signal():
    """Test mean reversion strategy generates long position when oversold."""
    strategy = MeanReversionStrategy(zscore_threshold=1.0)

    market_data = {"SPY": {"price": 450.0, "zscore": -1.5}}

    intents = strategy.generate_intents(["SPY"], market_data)

    assert len(intents) == 1
    assert intents[0].symbol == "SPY"
    assert intents[0].target_quantity == 1
    assert intents[0].conviction > 0
    assert "Oversold" in intents[0].reason


def test_mean_reversion_overbought_signal():
    """Test mean reversion strategy generates flat position when overbought."""
    strategy = MeanReversionStrategy(zscore_threshold=1.0)

    market_data = {"SPY": {"price": 450.0, "zscore": 1.5}}

    intents = strategy.generate_intents(["SPY"], market_data)

    assert len(intents) == 1
    assert intents[0].symbol == "SPY"
    assert intents[0].target_quantity == 0
    assert intents[0].conviction == 0.0
    assert "Overbought" in intents[0].reason


def test_mean_reversion_neutral_signal():
    """Test mean reversion strategy generates flat position in neutral zone."""
    strategy = MeanReversionStrategy(zscore_threshold=1.0)

    market_data = {"SPY": {"price": 450.0, "zscore": 0.5}}

    intents = strategy.generate_intents(["SPY"], market_data)

    assert len(intents) == 1
    assert intents[0].symbol == "SPY"
    assert intents[0].target_quantity == 0
    assert intents[0].conviction == 0.0
    assert "Neutral" in intents[0].reason


def test_strategy_handles_multiple_symbols():
    """Test strategies handle multiple symbols correctly."""
    strategy = TrendStrategy(ma_period=20)

    market_data = {
        "SPY": {"price": 450.0, "ma": 440.0},
        "QQQ": {"price": 380.0, "ma": 385.0},
        "AAPL": {"price": 175.0, "ma": 170.0},
    }

    intents = strategy.generate_intents(["SPY", "QQQ", "AAPL"], market_data)

    assert len(intents) == 3
    assert set(i.symbol for i in intents) == {"SPY", "QQQ", "AAPL"}


def test_position_intent_dataclass():
    """Test PositionIntent dataclass creation."""
    intent = PositionIntent(symbol="SPY", target_quantity=1, conviction=0.8, reason="Test reason")

    assert intent.symbol == "SPY"
    assert intent.target_quantity == 1
    assert intent.conviction == 0.8
    assert intent.reason == "Test reason"
