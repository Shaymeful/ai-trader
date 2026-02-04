"""Tests for execution gate tradability filter."""

import pytest
from decimal import Decimal

from src.app.execution.tradability_filter import (
    BlockReason,
    ExecutionGateConfig,
    TradabilityGate,
)
from src.market_data.fundamentals_cache import FundamentalsCache, TickerFundamentals


@pytest.fixture
def fundamentals_cache(tmp_path):
    """Create a fundamentals cache with test data."""
    cache = FundamentalsCache(cache_dir=tmp_path / "cache", ttl_hours=24)

    # Add test fundamentals
    test_fundamentals = [
        TickerFundamentals(
            symbol="MEGACAP",
            market_cap_usd=3_000_000_000_000,  # $3T - mega cap
            avg_dollar_volume_20d=10_000_000_000,
            price=500.0,
            spread_bps=2,
        ),
        TickerFundamentals(
            symbol="SMALLCAP",
            market_cap_usd=500_000_000,  # $500M - small cap
            avg_dollar_volume_20d=10_000_000,
            price=15.0,
            spread_bps=20,
        ),
        TickerFundamentals(
            symbol="MIDCAP",
            market_cap_usd=5_000_000_000,  # $5B - mid cap
            avg_dollar_volume_20d=100_000_000,
            price=45.0,
            spread_bps=10,
        ),
        TickerFundamentals(
            symbol="PENNY",
            market_cap_usd=100_000_000,  # $100M - small cap
            avg_dollar_volume_20d=1_000_000,
            price=0.50,  # Penny stock
            spread_bps=50,
        ),
        TickerFundamentals(
            symbol="ILLIQUID",
            market_cap_usd=800_000_000,  # $800M - small cap
            avg_dollar_volume_20d=500_000,  # Very low volume
            price=20.0,
            spread_bps=150,  # Very wide spread
        ),
    ]

    cache.bulk_set_fundamentals(test_fundamentals)
    return cache


def test_no_constraints_allows_all(fundamentals_cache):
    """Test that gate with no constraints allows all symbols."""
    config = ExecutionGateConfig()
    gate = TradabilityGate(config, fundamentals_cache)

    result = gate.check_tradability("MEGACAP", Decimal("500.0"))
    assert result.allowed is True

    result = gate.check_tradability("UNKNOWN", Decimal("100.0"))
    assert result.allowed is True


def test_market_cap_min_constraint(fundamentals_cache):
    """Test minimum market cap constraint."""
    config = ExecutionGateConfig(min_market_cap_usd=300_000_000)  # $300M min
    gate = TradabilityGate(config, fundamentals_cache)

    # Should allow: SMALLCAP ($500M), MIDCAP ($5B), MEGACAP ($3T)
    result = gate.check_tradability("SMALLCAP")
    assert result.allowed is True

    result = gate.check_tradability("MIDCAP")
    assert result.allowed is True

    result = gate.check_tradability("MEGACAP")
    assert result.allowed is True

    # Should block: PENNY ($100M < $300M min)
    result = gate.check_tradability("PENNY")
    assert result.allowed is False
    assert result.reason == BlockReason.MARKET_CAP_TOO_LOW


def test_market_cap_max_constraint(fundamentals_cache):
    """Test maximum market cap constraint."""
    config = ExecutionGateConfig(max_market_cap_usd=10_000_000_000)  # $10B max
    gate = TradabilityGate(config, fundamentals_cache)

    # Should allow: SMALLCAP ($500M), MIDCAP ($5B)
    result = gate.check_tradability("SMALLCAP")
    assert result.allowed is True

    result = gate.check_tradability("MIDCAP")
    assert result.allowed is True

    # Should block: MEGACAP ($3T > $10B max)
    result = gate.check_tradability("MEGACAP")
    assert result.allowed is False
    assert result.reason == BlockReason.MARKET_CAP_TOO_HIGH


def test_market_cap_range_constraint(fundamentals_cache):
    """Test market cap range constraint (small/mid cap targeting)."""
    config = ExecutionGateConfig(
        min_market_cap_usd=300_000_000,  # $300M min
        max_market_cap_usd=10_000_000_000,  # $10B max
    )
    gate = TradabilityGate(config, fundamentals_cache)

    # Should allow: SMALLCAP ($500M), MIDCAP ($5B)
    result = gate.check_tradability("SMALLCAP")
    assert result.allowed is True

    result = gate.check_tradability("MIDCAP")
    assert result.allowed is True

    # Should block: PENNY ($100M < min), MEGACAP ($3T > max)
    result = gate.check_tradability("PENNY")
    assert result.allowed is False
    assert result.reason == BlockReason.MARKET_CAP_TOO_LOW

    result = gate.check_tradability("MEGACAP")
    assert result.allowed is False
    assert result.reason == BlockReason.MARKET_CAP_TOO_HIGH


def test_price_min_constraint(fundamentals_cache):
    """Test minimum price constraint (avoid penny stocks)."""
    config = ExecutionGateConfig(min_price=3.0)
    gate = TradabilityGate(config, fundamentals_cache)

    # Should allow: SMALLCAP ($15), MIDCAP ($45)
    result = gate.check_tradability("SMALLCAP", Decimal("15.0"))
    assert result.allowed is True

    result = gate.check_tradability("MIDCAP", Decimal("45.0"))
    assert result.allowed is True

    # Should block: PENNY ($0.50 < $3.00 min)
    result = gate.check_tradability("PENNY", Decimal("0.50"))
    assert result.allowed is False
    assert result.reason == BlockReason.PRICE_TOO_LOW


def test_price_max_constraint(fundamentals_cache):
    """Test maximum price constraint."""
    config = ExecutionGateConfig(max_price=80.0)
    gate = TradabilityGate(config, fundamentals_cache)

    # Should allow: SMALLCAP ($15), MIDCAP ($45)
    result = gate.check_tradability("SMALLCAP", Decimal("15.0"))
    assert result.allowed is True

    result = gate.check_tradability("MIDCAP", Decimal("45.0"))
    assert result.allowed is True

    # Should block: MEGACAP ($500 > $80 max)
    result = gate.check_tradability("MEGACAP", Decimal("500.0"))
    assert result.allowed is False
    assert result.reason == BlockReason.PRICE_TOO_HIGH


def test_liquidity_constraint(fundamentals_cache):
    """Test minimum average dollar volume constraint."""
    config = ExecutionGateConfig(min_avg_dollar_volume_20d=5_000_000)  # $5M min
    gate = TradabilityGate(config, fundamentals_cache)

    # Should allow: SMALLCAP ($10M), MIDCAP ($100M), MEGACAP ($10B)
    result = gate.check_tradability("SMALLCAP")
    assert result.allowed is True

    result = gate.check_tradability("MIDCAP")
    assert result.allowed is True

    result = gate.check_tradability("MEGACAP")
    assert result.allowed is True

    # Should block: ILLIQUID ($500K < $5M min), PENNY ($1M < $5M min)
    result = gate.check_tradability("ILLIQUID")
    assert result.allowed is False
    assert result.reason == BlockReason.LIQUIDITY_TOO_LOW

    result = gate.check_tradability("PENNY")
    assert result.allowed is False
    assert result.reason == BlockReason.LIQUIDITY_TOO_LOW


def test_spread_constraint(fundamentals_cache):
    """Test maximum spread constraint."""
    config = ExecutionGateConfig(max_spread_bps=100)  # 1.00% max
    gate = TradabilityGate(config, fundamentals_cache)

    # Should allow: MEGACAP (2 bps), MIDCAP (10 bps), SMALLCAP (20 bps), PENNY (50 bps)
    result = gate.check_tradability("MEGACAP")
    assert result.allowed is True

    result = gate.check_tradability("MIDCAP")
    assert result.allowed is True

    result = gate.check_tradability("SMALLCAP")
    assert result.allowed is True

    result = gate.check_tradability("PENNY")
    assert result.allowed is True

    # Should block: ILLIQUID (150 bps > 100 bps max)
    result = gate.check_tradability("ILLIQUID")
    assert result.allowed is False
    assert result.reason == BlockReason.SPREAD_TOO_WIDE


def test_exclude_symbols(fundamentals_cache):
    """Test explicit exclude list."""
    config = ExecutionGateConfig(exclude_symbols=["MEGACAP", "MIDCAP"])
    gate = TradabilityGate(config, fundamentals_cache)

    # Should block: MEGACAP, MIDCAP (in exclude list)
    result = gate.check_tradability("MEGACAP")
    assert result.allowed is False
    assert result.reason == BlockReason.SYMBOL_EXCLUDED

    result = gate.check_tradability("MIDCAP")
    assert result.allowed is False
    assert result.reason == BlockReason.SYMBOL_EXCLUDED

    # Should allow: SMALLCAP (not in exclude list)
    result = gate.check_tradability("SMALLCAP")
    assert result.allowed is True


def test_allow_symbols_bypass(fundamentals_cache):
    """Test allow list bypasses all constraints."""
    config = ExecutionGateConfig(
        min_market_cap_usd=1_000_000_000_000,  # $1T min (would block all)
        allow_symbols=["MEGACAP"],  # But allow MEGACAP
    )
    gate = TradabilityGate(config, fundamentals_cache)

    # Should allow: MEGACAP (in allow list, bypasses market cap check)
    result = gate.check_tradability("MEGACAP")
    assert result.allowed is True
    assert "allow list" in result.message.lower()

    # Should block: SMALLCAP (not in allow list, fails market cap check)
    result = gate.check_tradability("SMALLCAP")
    assert result.allowed is False
    assert result.reason == BlockReason.MARKET_CAP_TOO_LOW


def test_small_cap_swing_profile(fundamentals_cache):
    """Test full small cap swing profile constraints."""
    config = ExecutionGateConfig(
        min_market_cap_usd=300_000_000,  # $300M min
        max_market_cap_usd=10_000_000_000,  # $10B max
        min_price=3.0,
        max_price=80.0,
        min_avg_dollar_volume_20d=5_000_000,  # $5M/day
        max_spread_bps=100,  # 1.00%
    )
    gate = TradabilityGate(config, fundamentals_cache)

    # Should allow: MIDCAP (passes all checks)
    result = gate.check_tradability("MIDCAP", Decimal("45.0"))
    assert result.allowed is True

    # Should block: MEGACAP (market cap too high)
    result = gate.check_tradability("MEGACAP", Decimal("500.0"))
    assert result.allowed is False
    assert result.reason == BlockReason.MARKET_CAP_TOO_HIGH

    # Should block: PENNY (market cap too low, price too low, liquidity too low)
    result = gate.check_tradability("PENNY", Decimal("0.50"))
    assert result.allowed is False
    # First violation wins (market cap in this case)
    assert result.reason == BlockReason.MARKET_CAP_TOO_LOW

    # Should block: ILLIQUID (liquidity too low, spread too wide)
    result = gate.check_tradability("ILLIQUID", Decimal("20.0"))
    assert result.allowed is False
    # First violation wins (liquidity)
    assert result.reason == BlockReason.LIQUIDITY_TOO_LOW


def test_fundamentals_unavailable_non_strict(fundamentals_cache):
    """Test behavior when fundamentals unavailable in non-strict mode."""
    config = ExecutionGateConfig(
        min_market_cap_usd=300_000_000,
        require_fundamentals=False,  # Allow unknown symbols
    )
    gate = TradabilityGate(config, fundamentals_cache)

    # Should allow: UNKNOWN (no fundamentals, but not required)
    result = gate.check_tradability("UNKNOWN", Decimal("50.0"))
    assert result.allowed is True


def test_fundamentals_unavailable_strict(fundamentals_cache):
    """Test behavior when fundamentals unavailable in strict mode."""
    config = ExecutionGateConfig(
        min_market_cap_usd=300_000_000,
        require_fundamentals=True,  # Block unknown symbols
    )
    gate = TradabilityGate(config, fundamentals_cache)

    # Should block: UNKNOWN (no fundamentals, required in strict mode)
    result = gate.check_tradability("UNKNOWN", Decimal("50.0"))
    assert result.allowed is False
    assert result.reason == BlockReason.FUNDAMENTALS_UNAVAILABLE


def test_batch_check_blocked_symbols(fundamentals_cache):
    """Test batch check for blocked symbols."""
    config = ExecutionGateConfig(
        min_market_cap_usd=300_000_000,
        max_market_cap_usd=10_000_000_000,
    )
    gate = TradabilityGate(config, fundamentals_cache)

    symbols = ["MEGACAP", "SMALLCAP", "MIDCAP", "PENNY"]
    blocked = gate.get_blocked_symbols(symbols)

    # Should block: MEGACAP (too high), PENNY (too low)
    assert "MEGACAP" in blocked
    assert "PENNY" in blocked
    assert "SMALLCAP" not in blocked
    assert "MIDCAP" not in blocked


def test_batch_check_allowed_symbols(fundamentals_cache):
    """Test batch check for allowed symbols."""
    config = ExecutionGateConfig(
        min_market_cap_usd=300_000_000,
        max_market_cap_usd=10_000_000_000,
    )
    gate = TradabilityGate(config, fundamentals_cache)

    symbols = ["MEGACAP", "SMALLCAP", "MIDCAP", "PENNY"]
    allowed = gate.get_allowed_symbols(symbols)

    # Should allow: SMALLCAP, MIDCAP
    assert "SMALLCAP" in allowed
    assert "MIDCAP" in allowed
    assert "MEGACAP" not in allowed
    assert "PENNY" not in allowed
