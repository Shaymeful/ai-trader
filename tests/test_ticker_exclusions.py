"""Tests for ticker exclusion manager (bad news handling)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.app.ticker_exclusions import TickerExclusion, TickerExclusionManager


@pytest.fixture
def temp_exclusions_dir(tmp_path):
    """Create temporary directory for exclusions."""
    exclusions_dir = tmp_path / "exclusions"
    exclusions_dir.mkdir()
    return exclusions_dir


@pytest.fixture
def exclusion_manager(temp_exclusions_dir):
    """Create ticker exclusion manager with temp files."""
    exclusions_file = temp_exclusions_dir / "exclusions.json"
    evaluations_file = temp_exclusions_dir / "evaluations.jsonl"

    return TickerExclusionManager(
        exclusions_file=exclusions_file,
        evaluations_file=evaluations_file,
    )


def test_add_exclusion(exclusion_manager):
    """Test adding a ticker exclusion."""
    exclusion = exclusion_manager.add_exclusion(
        symbol="TSLA",
        action="exclude",
        confidence=0.85,
        rationale="CEO investigated for fraud",
        ttl_hours=48,
        categories=["regulatory", "fraud"],
        source="ai_evaluator",
    )

    assert exclusion.symbol == "TSLA"
    assert exclusion.action == "exclude"
    assert exclusion.confidence == 0.85
    assert exclusion.ttl_hours == 48

    # Should be in exclusions dict
    assert "TSLA" in exclusion_manager.exclusions

    # Should be marked as excluded
    assert exclusion_manager.is_excluded("TSLA")


def test_remove_exclusion(exclusion_manager):
    """Test removing a ticker exclusion."""
    # Add exclusion
    exclusion_manager.add_exclusion(
        symbol="TSLA",
        action="exclude",
        confidence=0.80,
        rationale="Bad news",
        ttl_hours=24,
    )

    assert exclusion_manager.is_excluded("TSLA")

    # Remove exclusion
    removed = exclusion_manager.remove_exclusion("TSLA")

    assert removed is True
    assert not exclusion_manager.is_excluded("TSLA")
    assert "TSLA" not in exclusion_manager.exclusions


def test_exclusion_expiry(exclusion_manager):
    """Test that exclusions expire after TTL."""
    # Add exclusion with short TTL (already expired)
    now = datetime.now(UTC)
    expired_time = now - timedelta(hours=25)

    exclusion = TickerExclusion(
        symbol="TSLA",
        action="exclude",
        confidence=0.80,
        rationale="Old news",
        ttl_hours=24,
        expires_at=expired_time,
        created_at=expired_time - timedelta(hours=24),
        categories=["news"],
        source="ai_evaluator",
    )

    exclusion_manager.exclusions["TSLA"] = exclusion
    exclusion_manager.save()

    # Reload - should auto-remove expired
    exclusion_manager.load()

    assert "TSLA" not in exclusion_manager.exclusions
    assert not exclusion_manager.is_excluded("TSLA")


def test_is_excluded_checks_expiry(exclusion_manager):
    """Test that is_excluded() checks and removes expired exclusions."""
    # Add exclusion
    exclusion_manager.add_exclusion(
        symbol="TSLA",
        action="exclude",
        confidence=0.80,
        rationale="Test",
        ttl_hours=24,
    )

    # Manually expire it
    exclusion_manager.exclusions["TSLA"].expires_at = datetime.now(UTC) - timedelta(hours=1)

    # is_excluded should detect expiry and remove
    is_excluded = exclusion_manager.is_excluded("TSLA")

    assert not is_excluded
    assert "TSLA" not in exclusion_manager.exclusions


def test_get_exclusion(exclusion_manager):
    """Test getting exclusion details."""
    exclusion_manager.add_exclusion(
        symbol="TSLA",
        action="exclude",
        confidence=0.85,
        rationale="CEO fraud investigation",
        ttl_hours=48,
        categories=["regulatory", "fraud"],
    )

    exclusion = exclusion_manager.get_exclusion("TSLA")

    assert exclusion is not None
    assert exclusion.symbol == "TSLA"
    assert exclusion.confidence == 0.85
    assert "fraud" in exclusion.categories


def test_get_exclusion_not_found(exclusion_manager):
    """Test getting non-existent exclusion returns None."""
    exclusion = exclusion_manager.get_exclusion("NONEXISTENT")

    assert exclusion is None


def test_get_all_exclusions(exclusion_manager):
    """Test getting all active exclusions."""
    # Add multiple exclusions
    exclusion_manager.add_exclusion(
        symbol="TSLA",
        action="exclude",
        confidence=0.85,
        rationale="Bad news 1",
        ttl_hours=48,
    )

    exclusion_manager.add_exclusion(
        symbol="NKLA",
        action="exclude",
        confidence=0.90,
        rationale="Bad news 2",
        ttl_hours=72,
    )

    # Add one that will expire
    exclusion_manager.add_exclusion(
        symbol="EXPIRED",
        action="exclude",
        confidence=0.75,
        rationale="Old news",
        ttl_hours=24,
    )
    exclusion_manager.exclusions["EXPIRED"].expires_at = datetime.now(UTC) - timedelta(hours=1)

    all_exclusions = exclusion_manager.get_all_exclusions()

    # Should have 2 active (expired one removed)
    assert len(all_exclusions) == 2
    assert "TSLA" in all_exclusions
    assert "NKLA" in all_exclusions
    assert "EXPIRED" not in all_exclusions


def test_should_evaluate_rate_limiting(exclusion_manager):
    """Test rate limiting prevents frequent re-evaluation."""
    # Add recent exclusion
    exclusion_manager.add_exclusion(
        symbol="TSLA",
        action="exclude",
        confidence=0.80,
        rationale="Recent news",
        ttl_hours=48,
    )

    # Should not allow re-evaluation within min_interval
    should_eval = exclusion_manager.should_evaluate("TSLA", min_interval_hours=24)

    assert not should_eval


def test_should_evaluate_allows_after_interval(exclusion_manager):
    """Test rate limiting allows re-evaluation after interval."""
    # Add old exclusion
    exclusion_manager.add_exclusion(
        symbol="TSLA",
        action="exclude",
        confidence=0.80,
        rationale="Old news",
        ttl_hours=48,
    )

    # Manually set created_at to 25 hours ago
    exclusion_manager.exclusions["TSLA"].created_at = datetime.now(UTC) - timedelta(hours=25)

    # Should allow re-evaluation after 24 hours
    should_eval = exclusion_manager.should_evaluate("TSLA", min_interval_hours=24)

    assert should_eval


def test_should_evaluate_new_ticker(exclusion_manager):
    """Test rate limiting allows evaluation of new ticker."""
    # Ticker with no history
    should_eval = exclusion_manager.should_evaluate("NEWSTOCK", min_interval_hours=24)

    assert should_eval


def test_persistence(exclusion_manager, temp_exclusions_dir):
    """Test exclusions persist across manager instances."""
    # Add exclusion
    exclusion_manager.add_exclusion(
        symbol="TSLA",
        action="exclude",
        confidence=0.85,
        rationale="Persistent exclusion",
        ttl_hours=48,
        categories=["fraud"],
    )

    # Create new manager instance (loads from disk)
    exclusions_file = temp_exclusions_dir / "exclusions.json"
    evaluations_file = temp_exclusions_dir / "evaluations.jsonl"

    new_manager = TickerExclusionManager(
        exclusions_file=exclusions_file,
        evaluations_file=evaluations_file,
    )

    # Should have loaded the exclusion
    assert "TSLA" in new_manager.exclusions
    assert new_manager.is_excluded("TSLA")

    exclusion = new_manager.get_exclusion("TSLA")
    assert exclusion.confidence == 0.85
    assert "fraud" in exclusion.categories


def test_evaluation_history_logged(exclusion_manager, temp_exclusions_dir):
    """Test evaluations are logged to JSONL history."""
    # Add exclusion
    exclusion_manager.add_exclusion(
        symbol="TSLA",
        action="exclude",
        confidence=0.85,
        rationale="CEO fraud investigation",
        ttl_hours=48,
        categories=["regulatory", "fraud"],
        source="ai_evaluator",
    )

    # Check history file
    evaluations_file = temp_exclusions_dir / "evaluations.jsonl"
    assert evaluations_file.exists()

    # Read history
    with open(evaluations_file) as f:
        lines = f.readlines()

    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["symbol"] == "TSLA"
    assert entry["action"] == "exclude"
    assert entry["confidence"] == 0.85
    assert "fraud" in entry["categories"]


def test_get_excluded_dict(exclusion_manager):
    """Test get_excluded_dict returns format for reconciler."""
    # Add multiple exclusions with different actions
    exclusion_manager.add_exclusion(
        symbol="TSLA",
        action="exclude",
        confidence=0.85,
        rationale="Bad news",
        ttl_hours=48,
        categories=["fraud"],
    )

    exclusion_manager.add_exclusion(
        symbol="AAPL",
        action="watch",  # Not excluded, just watching
        confidence=0.60,
        rationale="Minor news",
        ttl_hours=24,
    )

    excluded_dict = exclusion_manager.get_excluded_dict()

    # Should only include "exclude" actions
    assert "TSLA" in excluded_dict
    assert "AAPL" not in excluded_dict

    # Check format
    tsla_info = excluded_dict["TSLA"]
    assert tsla_info["reason"] == "Bad news"
    assert tsla_info["confidence"] == 0.85
    assert tsla_info["ttl_hours"] == 48
    assert "fraud" in tsla_info["categories"]
    assert "expires_at" in tsla_info
