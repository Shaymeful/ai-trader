"""Tests for candidate system (schema, filtering, attribution)."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.app.candidates.schema import Action, Candidate, Horizon, load_snapshot, write_snapshot
from src.app.candidates.store import (
    deduplicate,
    filter_by_liquidity,
    filter_valid,
    get_tradeable_candidates,
    load_candidates,
)


class TestCandidateSchema:
    """Tests for Candidate model validation."""

    def test_valid_candidate(self):
        """Test creating a valid candidate."""
        now = datetime.now(UTC).replace(tzinfo=None)
        expires = now + timedelta(hours=6)

        candidate = Candidate(
            candidate_id="test-001",
            created_at=now.isoformat() + "Z",
            expires_at=expires.isoformat() + "Z",
            symbol="AAPL",
            action=Action.BUY,
            confidence=0.85,
            horizon=Horizon.INTRADAY,
            sector="Technology",
            event_type="earnings_beat",
            tags=["momentum", "breakout"],
            reason="Strong earnings",
            avg_dollar_volume=50_000_000_000.0,
        )

        assert candidate.symbol == "AAPL"
        assert candidate.action == Action.BUY
        assert candidate.confidence == 0.85
        assert candidate.is_tradeable()
        assert not candidate.is_expired(now)

    def test_invalid_confidence_range(self):
        """Test that confidence must be 0.0-1.0."""
        now = datetime.now(UTC).replace(tzinfo=None)
        expires = now + timedelta(hours=6)

        with pytest.raises(ValueError):
            Candidate(
                candidate_id="test-001",
                created_at=now.isoformat() + "Z",
                expires_at=expires.isoformat() + "Z",
                symbol="AAPL",
                action=Action.BUY,
                confidence=1.5,  # Invalid: > 1.0
                horizon=Horizon.INTRADAY,
            )

    def test_invalid_timestamp_format(self):
        """Test that invalid ISO 8601 timestamps are rejected."""
        with pytest.raises(ValueError):
            Candidate(
                candidate_id="test-001",
                created_at="not-a-timestamp",
                expires_at="2026-01-01T12:00:00Z",
                symbol="AAPL",
                action=Action.BUY,
                confidence=0.85,
                horizon=Horizon.INTRADAY,
            )

    def test_is_tradeable(self):
        """Test is_tradeable() method."""
        now = datetime.now(UTC).replace(tzinfo=None)
        expires = now + timedelta(hours=6)

        buy_candidate = Candidate(
            candidate_id="buy-001",
            created_at=now.isoformat() + "Z",
            expires_at=expires.isoformat() + "Z",
            symbol="AAPL",
            action=Action.BUY,
            confidence=0.85,
            horizon=Horizon.INTRADAY,
        )

        sell_candidate = Candidate(
            candidate_id="sell-001",
            created_at=now.isoformat() + "Z",
            expires_at=expires.isoformat() + "Z",
            symbol="AAPL",
            action=Action.SELL,
            confidence=0.85,
            horizon=Horizon.INTRADAY,
        )

        watch_candidate = Candidate(
            candidate_id="watch-001",
            created_at=now.isoformat() + "Z",
            expires_at=expires.isoformat() + "Z",
            symbol="TSLA",
            action=Action.WATCH,
            confidence=0.65,
            horizon=Horizon.INTRADAY,
        )

        assert buy_candidate.is_tradeable()
        assert sell_candidate.is_tradeable()
        assert not watch_candidate.is_tradeable()

    def test_is_expired(self):
        """Test is_expired() method."""
        now = datetime.now(UTC).replace(tzinfo=None)
        past = now - timedelta(hours=1)
        future = now + timedelta(hours=6)

        expired_candidate = Candidate(
            candidate_id="expired-001",
            created_at=past.isoformat() + "Z",
            expires_at=past.isoformat() + "Z",
            symbol="AAPL",
            action=Action.BUY,
            confidence=0.85,
            horizon=Horizon.INTRADAY,
        )

        valid_candidate = Candidate(
            candidate_id="valid-001",
            created_at=now.isoformat() + "Z",
            expires_at=future.isoformat() + "Z",
            symbol="AAPL",
            action=Action.BUY,
            confidence=0.85,
            horizon=Horizon.INTRADAY,
        )

        assert expired_candidate.is_expired(now)
        assert not valid_candidate.is_expired(now)


class TestCandidateStorage:
    """Tests for candidate snapshot storage."""

    def test_write_and_load_snapshot(self):
        """Test writing and loading candidates from snapshot."""
        now = datetime.now(UTC).replace(tzinfo=None)
        expires = now + timedelta(hours=6)

        candidates = [
            Candidate(
                candidate_id="test-001",
                created_at=now.isoformat() + "Z",
                expires_at=expires.isoformat() + "Z",
                symbol="AAPL",
                action=Action.BUY,
                confidence=0.85,
                horizon=Horizon.INTRADAY,
            ),
            Candidate(
                candidate_id="test-002",
                created_at=now.isoformat() + "Z",
                expires_at=expires.isoformat() + "Z",
                symbol="SPY",
                action=Action.BUY,
                confidence=0.72,
                horizon=Horizon.SWING,
            ),
        ]

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            temp_path = Path(f.name)

        try:
            # Write snapshot
            write_snapshot(candidates, temp_path, metadata={"source": "test"})

            # Load snapshot
            loaded = load_snapshot(temp_path)

            assert len(loaded) == 2
            assert loaded[0].candidate_id == "test-001"
            assert loaded[0].symbol == "AAPL"
            assert loaded[1].candidate_id == "test-002"
            assert loaded[1].symbol == "SPY"
        finally:
            temp_path.unlink()

    def test_load_nonexistent_snapshot(self):
        """Test that loading nonexistent snapshot raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_snapshot("nonexistent.json")

    def test_load_candidates_safe_fallback(self):
        """Test that load_candidates() returns empty list for missing file."""
        candidates = load_candidates("nonexistent.json")
        assert candidates == []


class TestCandidateFiltering:
    """Tests for candidate filtering functions."""

    def test_filter_valid(self):
        """Test filtering by expiration."""
        now = datetime.now(UTC).replace(tzinfo=None)
        past = now - timedelta(hours=1)
        future = now + timedelta(hours=6)

        candidates = [
            Candidate(
                candidate_id="expired-001",
                created_at=past.isoformat() + "Z",
                expires_at=past.isoformat() + "Z",
                symbol="AAPL",
                action=Action.BUY,
                confidence=0.85,
                horizon=Horizon.INTRADAY,
            ),
            Candidate(
                candidate_id="valid-001",
                created_at=now.isoformat() + "Z",
                expires_at=future.isoformat() + "Z",
                symbol="SPY",
                action=Action.BUY,
                confidence=0.72,
                horizon=Horizon.SWING,
            ),
        ]

        valid = filter_valid(candidates, now)
        assert len(valid) == 1
        assert valid[0].candidate_id == "valid-001"

    def test_filter_by_liquidity(self):
        """Test filtering by average dollar volume."""
        now = datetime.now(UTC).replace(tzinfo=None)
        expires = now + timedelta(hours=6)

        candidates = [
            Candidate(
                candidate_id="liquid-001",
                created_at=now.isoformat() + "Z",
                expires_at=expires.isoformat() + "Z",
                symbol="AAPL",
                action=Action.BUY,
                confidence=0.85,
                horizon=Horizon.INTRADAY,
                avg_dollar_volume=50_000_000_000.0,
            ),
            Candidate(
                candidate_id="illiquid-001",
                created_at=now.isoformat() + "Z",
                expires_at=expires.isoformat() + "Z",
                symbol="TINY",
                action=Action.BUY,
                confidence=0.75,
                horizon=Horizon.INTRADAY,
                avg_dollar_volume=500_000.0,
            ),
            Candidate(
                candidate_id="no-volume-data",
                created_at=now.isoformat() + "Z",
                expires_at=expires.isoformat() + "Z",
                symbol="SPY",
                action=Action.BUY,
                confidence=0.72,
                horizon=Horizon.SWING,
                avg_dollar_volume=None,
            ),
        ]

        liquid = filter_by_liquidity(candidates, min_dollar_volume=1_000_000.0)
        assert len(liquid) == 2  # AAPL and SPY (no data = pass through)
        assert {c.candidate_id for c in liquid} == {"liquid-001", "no-volume-data"}

    def test_deduplicate(self):
        """Test deduplication by candidate_id, keeping newest."""
        now = datetime.now(UTC).replace(tzinfo=None)
        later = now + timedelta(minutes=10)
        expires = now + timedelta(hours=6)

        candidates = [
            Candidate(
                candidate_id="dup-001",
                created_at=now.isoformat() + "Z",
                expires_at=expires.isoformat() + "Z",
                symbol="AAPL",
                action=Action.BUY,
                confidence=0.80,
                horizon=Horizon.INTRADAY,
            ),
            Candidate(
                candidate_id="dup-001",
                created_at=later.isoformat() + "Z",
                expires_at=expires.isoformat() + "Z",
                symbol="AAPL",
                action=Action.BUY,
                confidence=0.90,  # Updated confidence
                horizon=Horizon.INTRADAY,
            ),
            Candidate(
                candidate_id="unique-001",
                created_at=now.isoformat() + "Z",
                expires_at=expires.isoformat() + "Z",
                symbol="SPY",
                action=Action.BUY,
                confidence=0.72,
                horizon=Horizon.SWING,
            ),
        ]

        deduped = deduplicate(candidates)
        assert len(deduped) == 2
        # Should keep the newer candidate with confidence 0.90
        dup_candidate = next(c for c in deduped if c.candidate_id == "dup-001")
        assert dup_candidate.confidence == 0.90

    def test_get_tradeable_candidates_full_pipeline(self):
        """Test full filtering pipeline."""
        now = datetime.now(UTC).replace(tzinfo=None)
        past = now - timedelta(hours=1)
        future = now + timedelta(hours=6)

        candidates = [
            # Valid, liquid, tradeable (BUY)
            Candidate(
                candidate_id="good-001",
                created_at=now.isoformat() + "Z",
                expires_at=future.isoformat() + "Z",
                symbol="AAPL",
                action=Action.BUY,
                confidence=0.85,
                horizon=Horizon.INTRADAY,
                avg_dollar_volume=50_000_000_000.0,
            ),
            # Expired (should be filtered out)
            Candidate(
                candidate_id="expired-001",
                created_at=past.isoformat() + "Z",
                expires_at=past.isoformat() + "Z",
                symbol="MSFT",
                action=Action.BUY,
                confidence=0.80,
                horizon=Horizon.INTRADAY,
                avg_dollar_volume=40_000_000_000.0,
            ),
            # Illiquid (should be filtered out)
            Candidate(
                candidate_id="illiquid-001",
                created_at=now.isoformat() + "Z",
                expires_at=future.isoformat() + "Z",
                symbol="TINY",
                action=Action.BUY,
                confidence=0.75,
                horizon=Horizon.INTRADAY,
                avg_dollar_volume=500_000.0,
            ),
            # Not tradeable - WATCH action (should be filtered out)
            Candidate(
                candidate_id="watch-001",
                created_at=now.isoformat() + "Z",
                expires_at=future.isoformat() + "Z",
                symbol="TSLA",
                action=Action.WATCH,
                confidence=0.65,
                horizon=Horizon.INTRADAY,
                avg_dollar_volume=15_000_000_000.0,
            ),
            # Valid, liquid, tradeable (SELL)
            Candidate(
                candidate_id="good-002",
                created_at=now.isoformat() + "Z",
                expires_at=future.isoformat() + "Z",
                symbol="SPY",
                action=Action.SELL,
                confidence=0.78,
                horizon=Horizon.SWING,
                avg_dollar_volume=25_000_000_000.0,
            ),
        ]

        tradeable = get_tradeable_candidates(candidates, now, min_dollar_volume=1_000_000.0)

        assert len(tradeable) == 2
        assert {c.candidate_id for c in tradeable} == {"good-001", "good-002"}
        assert all(c.is_tradeable() for c in tradeable)
        assert all(not c.is_expired(now) for c in tradeable)


class TestCandidatePropagation:
    """Tests for candidate_id propagation through intents."""

    def test_intent_includes_candidate_id(self):
        """Test that PositionIntent includes candidate_id."""
        from src.app.strategies.base import PositionIntent

        intent = PositionIntent(
            symbol="AAPL",
            target_quantity=1,
            conviction=0.85,
            reason="Strong signal",
            candidate_id="test-001",
        )

        assert intent.candidate_id == "test-001"

    def test_intent_optional_candidate_id(self):
        """Test that candidate_id is optional (backward compatible)."""
        from src.app.strategies.base import PositionIntent

        intent = PositionIntent(
            symbol="AAPL",
            target_quantity=1,
            conviction=0.85,
            reason="Strong signal",
        )

        assert intent.candidate_id is None

    def test_strategy_propagates_candidate_id(self):
        """Test that strategies propagate candidate_id to intents."""
        from src.app.strategies.trend import TrendStrategy

        strategy = TrendStrategy(ma_period=20)
        universe = ["AAPL"]
        market_data = {
            "AAPL": {
                "price": 150.0,
                "ma": 145.0,  # Price > MA = bullish
            }
        }
        candidate_map = {"AAPL": "test-candidate-001"}

        intents = strategy.generate_intents(universe, market_data, candidate_map)

        assert len(intents) == 1
        assert intents[0].candidate_id == "test-candidate-001"


class TestLedgerEvents:
    """Tests for candidate-related ledger events."""

    def test_candidate_loaded_event(self):
        """Test CandidateLoadedEvent creation and serialization."""
        from src.app.ledger import CandidateLoadedEvent

        event = CandidateLoadedEvent(
            count_total=3,
            count_tradeable=2,
            symbols=["AAPL", "SPY"],
            snapshot_path="out/selector/snapshot.json",
        )

        assert event.event_type == "candidate_loaded"
        assert event.count_total == 3
        assert event.count_tradeable == 2
        assert event.symbols == ["AAPL", "SPY"]
        assert event.snapshot_path == "out/selector/snapshot.json"
        assert event.event_id is not None
        assert event.timestamp is not None

    def test_strategy_intent_created_event(self):
        """Test StrategyIntentCreatedEvent with candidate_id."""
        from src.app.ledger import StrategyIntentCreatedEvent

        event = StrategyIntentCreatedEvent(
            strategy_id="Trend_MA20",
            version=1,
            symbol="AAPL",
            target_quantity=1,
            conviction=0.85,
            reason="Price > MA",
            candidate_id="test-001",
        )

        assert event.event_type == "strategy_intent_created"
        assert event.strategy_id == "Trend_MA20"
        assert event.candidate_id == "test-001"

    def test_strategy_intent_created_event_no_candidate(self):
        """Test StrategyIntentCreatedEvent without candidate_id (backward compatible)."""
        from src.app.ledger import StrategyIntentCreatedEvent

        event = StrategyIntentCreatedEvent(
            strategy_id="Trend_MA20",
            version=1,
            symbol="AAPL",
            target_quantity=1,
            conviction=0.85,
            reason="Price > MA",
        )

        assert event.candidate_id is None

    def test_order_placed_event_with_candidate_id(self):
        """Test OrderPlacedEvent includes candidate_id."""
        from decimal import Decimal

        from src.app.ledger import OrderPlacedEvent

        event = OrderPlacedEvent(
            strategy_id="Trend_MA20",
            version=1,
            client_order_id="order-123",
            symbol="AAPL",
            side="buy",
            quantity=Decimal("1"),
            order_type="market",
            candidate_id="test-001",
        )

        assert event.event_type == "order_placed"
        assert event.candidate_id == "test-001"
