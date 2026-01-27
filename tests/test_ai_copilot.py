"""
Unit tests for AI Co-Pilot advisory layer.

Tests:
- Budget gates
- Graceful degradation (no exceptions)
- Config loading
- Feature toggles
- Status tracking
- All LLM calls mocked (no real API calls)
"""

import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from src.app.candidates.schema import Action, Candidate, Horizon
from src.app.config import Config
from src.app.llm_advisors.client import CoPilotClient
from src.app.llm_advisors.daily_journal import generate_daily_journal, should_generate_journal
from src.app.llm_advisors.status import StatusSnapshot, load_latest_status
from src.app.llm_advisors.strategy_critique import (
    generate_strategy_critique,
    load_recent_critiques,
)
from src.app.llm_advisors.trade_rationale import (
    TradeRationaleResult,
    enrich_candidates_with_rationale,
    generate_trade_rationale,
)
from tests.mocks.mock_llm_provider import MockLLMProvider


@pytest.fixture
def mock_config():
    """Create mock config with AI Co-Pilot enabled."""
    config = MagicMock(spec=Config)
    config.ai_copilot_enabled = True
    config.ai_copilot_influence_decisions = False
    config.ai_copilot_model = "gpt-4o-mini"
    config.ai_copilot_max_calls_per_run = 3
    config.ai_copilot_max_output_tokens = 350
    config.ai_copilot_timeout_s = 20
    config.ai_copilot_trade_rationale_enabled = True
    config.ai_copilot_daily_journal_enabled = True
    config.ai_copilot_strategy_critique_enabled = True
    return config


@pytest.fixture
def mock_disabled_config():
    """Create mock config with AI Co-Pilot disabled."""
    config = MagicMock(spec=Config)
    config.ai_copilot_enabled = False
    config.ai_copilot_influence_decisions = False
    config.ai_copilot_model = "gpt-4o-mini"
    config.ai_copilot_max_calls_per_run = 3
    config.ai_copilot_max_output_tokens = 350
    config.ai_copilot_timeout_s = 20
    config.ai_copilot_trade_rationale_enabled = True
    config.ai_copilot_daily_journal_enabled = True
    config.ai_copilot_strategy_critique_enabled = True
    return config


@pytest.fixture
def sample_candidate():
    """Create sample candidate for testing."""
    return Candidate(
        candidate_id="test-123",
        created_at="2024-01-01T10:00:00Z",
        expires_at="2024-01-01T16:00:00Z",
        symbol="AAPL",
        action=Action.BUY,
        confidence=0.85,
        horizon=Horizon.SWING,
        sector="Technology",
        event_type="news",
        reason="Strong earnings beat",
    )


# ============================================================================
# CoPilotClient Tests
# ============================================================================


def test_copilot_client_initialization(mock_config):
    """Test CoPilot client initializes correctly."""
    client = CoPilotClient(mock_config)

    assert client.config == mock_config
    assert client.call_count == 0
    assert client.dry_run == False
    assert client._provider is None  # Lazy initialization


def test_copilot_client_dry_run_mode(mock_config, monkeypatch):
    """Test dry run mode prevents real LLM calls."""
    monkeypatch.setenv("AI_COPILOT_DRY_RUN", "1")

    client = CoPilotClient(mock_config)
    assert client.dry_run == True

    # Call should return mock data
    result = client.generate_advisory_json(
        prompt="test",
        schema={"type": "object"},
        feature_name="test",
    )

    assert result is not None
    assert result["dry_run"] == True
    assert result["feature"] == "test"
    assert client.call_count == 1  # Budget still tracked


def test_copilot_client_budget_gate(mock_config):
    """Test budget gate prevents excessive LLM calls."""
    client = CoPilotClient(mock_config)
    client.reset_budget()

    # Mock provider
    mock_provider = MockLLMProvider(responses={"result": "success"})

    with patch.object(client, "_get_provider", return_value=mock_provider):
        # Make max_calls_per_run calls
        for i in range(mock_config.ai_copilot_max_calls_per_run):
            result = client.generate_advisory_json(
                prompt=f"test {i}",
                schema={"type": "object"},
                feature_name="test",
            )
            assert result is not None

        # Next call should be blocked by budget
        result = client.generate_advisory_json(
            prompt="should fail",
            schema={"type": "object"},
            feature_name="test",
        )
        assert result is None
        assert client.call_count == mock_config.ai_copilot_max_calls_per_run


def test_copilot_client_graceful_degradation(mock_config):
    """Test client never raises exceptions on LLM failures."""
    client = CoPilotClient(mock_config)

    # Mock provider that raises various exceptions
    mock_provider = MagicMock()
    mock_provider.generate_structured_json.side_effect = [
        TimeoutError("Timeout"),
        ValueError("Invalid schema"),
        Exception("Unknown error"),
    ]

    with patch.object(client, "_get_provider", return_value=mock_provider):
        # All calls should return None instead of raising
        for i in range(3):
            result = client.generate_advisory_json(
                prompt="test",
                schema={"type": "object"},
                feature_name="test",
                max_retries=1,  # Single retry to speed up test
            )
            assert result is None


def test_copilot_client_disabled(mock_disabled_config):
    """Test client skips calls when disabled."""
    client = CoPilotClient(mock_disabled_config)

    result = client.generate_advisory_json(
        prompt="test",
        schema={"type": "object"},
        feature_name="test",
    )

    assert result is None
    assert client.call_count == 0  # Budget not consumed


# ============================================================================
# TradeRationale Tests
# ============================================================================


def test_trade_rationale_generation(mock_config, sample_candidate):
    """Test trade rationale generation."""
    client = CoPilotClient(mock_config)

    # Mock provider with rationale response
    mock_provider = MockLLMProvider(
        responses={
            "rationale": "Strong technical momentum with earnings catalyst",
            "confidence": 85,
            "risk_factors": ["Market volatility", "Sector rotation risk"],
        }
    )

    with patch.object(client, "_get_provider", return_value=mock_provider):
        result = generate_trade_rationale(sample_candidate, client, mock_config)

        assert result.success == True
        assert result.candidate_id == sample_candidate.candidate_id
        assert result.rationale is not None
        assert result.confidence == 85
        assert len(result.risk_factors) == 2


def test_trade_rationale_disabled(mock_config, sample_candidate):
    """Test rationale skipped when feature disabled."""
    mock_config.ai_copilot_trade_rationale_enabled = False
    client = CoPilotClient(mock_config)

    result = generate_trade_rationale(sample_candidate, client, mock_config)

    assert result.success == False
    assert result.rationale is None


def test_enrich_candidates_budget_aware(mock_config):
    """Test candidate enrichment respects budget."""
    # Create 10 candidates, but budget only allows 3 calls
    candidates = [
        Candidate(
            candidate_id=f"test-{i}",
            created_at="2024-01-01T10:00:00Z",
            expires_at="2024-01-01T16:00:00Z",
            symbol=f"SYM{i}",
            action=Action.BUY,
            confidence=0.8 + i * 0.01,
            horizon=Horizon.SWING,
        )
        for i in range(10)
    ]

    client = CoPilotClient(mock_config)
    client.reset_budget()

    mock_provider = MockLLMProvider(
        responses={
            "rationale": "Test rationale",
            "confidence": 80,
            "risk_factors": ["Test risk"],
        }
    )

    with patch.object(client, "_get_provider", return_value=mock_provider):
        results = enrich_candidates_with_rationale(candidates, client, mock_config, max_candidates=10)

        # Should only enrich up to budget limit
        assert len(results) <= mock_config.ai_copilot_max_calls_per_run
        assert client.call_count <= mock_config.ai_copilot_max_calls_per_run


# ============================================================================
# DailyJournal Tests
# ============================================================================


def test_daily_journal_generation(mock_config, tmp_path, monkeypatch):
    """Test daily journal generation."""
    # Use tmp_path for journal output
    monkeypatch.chdir(tmp_path)

    client = CoPilotClient(mock_config)

    summary_data = {
        "positions_opened": ["AAPL", "MSFT"],
        "positions_closed": ["GOOGL"],
        "realized_pnl": 150.50,
        "unrealized_pnl": -25.00,
        "total_trades": 3,
        "win_rate": 0.667,
    }

    mock_provider = MockLLMProvider(
        responses={
            "title": "Trading Journal - 2024-01-01",
            "summary": "Solid day with 2 new positions opened",
            "highlights": ["Strong tech momentum", "Profitable exit on GOOGL"],
            "performance": "2/3 trades profitable, +$150 realized",
            "lessons": ["Wait for better entry on MSFT"],
            "outlook": "Watch for sector rotation signals",
        }
    )

    with patch.object(client, "_get_provider", return_value=mock_provider):
        journal_path = generate_daily_journal(
            client, mock_config, date_str="2024-01-01", summary_data=summary_data
        )

        assert journal_path is not None
        assert Path(journal_path).exists()

        # Verify markdown content
        content = Path(journal_path).read_text()
        assert "Trading Journal" in content
        assert "2024-01-01" in content
        assert "$150.50" in content  # Realized P&L from metrics
        assert "66.7%" in content  # Win rate from metrics


def test_daily_journal_idempotency(mock_config, tmp_path, monkeypatch):
    """Test journal not regenerated if already exists."""
    monkeypatch.chdir(tmp_path)

    client = CoPilotClient(mock_config)

    # Create existing journal
    journal_dir = Path("logs/journal")
    journal_dir.mkdir(parents=True, exist_ok=True)
    existing_journal = journal_dir / "2024-01-01.md"
    existing_journal.write_text("Existing journal")

    # Should skip generation
    assert should_generate_journal("2024-01-01") == False

    # Generate should return existing path without calling LLM
    journal_path = generate_daily_journal(client, mock_config, date_str="2024-01-01")

    assert journal_path == str(existing_journal)
    assert client.call_count == 0  # No LLM call made


def test_daily_journal_disabled(mock_disabled_config):
    """Test journal skipped when feature disabled."""
    mock_disabled_config.ai_copilot_daily_journal_enabled = False
    client = CoPilotClient(mock_disabled_config)

    journal_path = generate_daily_journal(client, mock_disabled_config)

    assert journal_path is None


# ============================================================================
# StrategyCritique Tests
# ============================================================================


def test_strategy_critique_generation(mock_config, tmp_path, monkeypatch):
    """Test strategy critique generation."""
    monkeypatch.chdir(tmp_path)

    client = CoPilotClient(mock_config)

    performance_data = {
        "total_trades": 5,
        "win_rate": 0.60,
        "realized_pnl": 250.00,
        "avg_hold_time_hours": 4.5,
        "best_trade": "AAPL +$150",
        "worst_trade": "TSLA -$50",
    }

    mock_provider = MockLLMProvider(
        responses={
            "critique": "Decent win rate but holding too long on losers",
            "recommendations": ["Tighten stop losses", "Take profits earlier"],
            "confidence": 75,
            "strengths": ["Good entry timing", "Proper position sizing"],
            "weaknesses": ["Exit discipline needs work"],
        }
    )

    with patch.object(client, "_get_provider", return_value=mock_provider):
        success = generate_strategy_critique(
            client, mock_config, date_str="2024-01-01", performance_data=performance_data
        )

        assert success == True

        # Verify JSONL entry
        memory_path = Path("data/strategy_memory.jsonl")
        assert memory_path.exists()

        entries = []
        with open(memory_path) as f:
            for line in f:
                entries.append(json.loads(line))

        assert len(entries) == 1
        assert entries[0]["date"] == "2024-01-01"
        assert entries[0]["confidence"] == 75
        assert len(entries[0]["recommendations"]) == 2


def test_strategy_critique_idempotency(mock_config, tmp_path, monkeypatch):
    """Test critique not regenerated if already exists for date."""
    monkeypatch.chdir(tmp_path)

    client = CoPilotClient(mock_config)

    # Create existing critique
    memory_path = Path("data/strategy_memory.jsonl")
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    existing_entry = {
        "date": "2024-01-01",
        "critique": "Existing critique",
        "confidence": 80,
    }
    with open(memory_path, "w") as f:
        f.write(json.dumps(existing_entry) + "\n")

    # Should skip generation
    success = generate_strategy_critique(client, mock_config, date_str="2024-01-01")

    assert success == True
    assert client.call_count == 0  # No LLM call made


def test_load_recent_critiques(tmp_path, monkeypatch):
    """Test loading recent critiques from memory."""
    monkeypatch.chdir(tmp_path)

    memory_path = Path("data/strategy_memory.jsonl")
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    # Write 10 critiques
    with open(memory_path, "w") as f:
        for i in range(10):
            entry = {
                "date": f"2024-01-{i+1:02d}",
                "critique": f"Critique {i}",
                "confidence": 70 + i,
            }
            f.write(json.dumps(entry) + "\n")

    # Load recent 5
    critiques = load_recent_critiques(memory_path, n=5)

    assert len(critiques) == 5
    # Should be most recent first
    assert critiques[0]["date"] == "2024-01-10"
    assert critiques[4]["date"] == "2024-01-06"


# ============================================================================
# StatusSnapshot Tests
# ============================================================================


def test_status_snapshot_creation(mock_config):
    """Test status snapshot creation."""
    client = CoPilotClient(mock_config)
    client.reset_budget()

    snapshot = StatusSnapshot(client, mock_config)

    # Record some activity
    snapshot.record_trade_rationale_call(success=True)
    snapshot.record_trade_rationale_call(success=False)
    snapshot.record_daily_journal_generated()

    status = snapshot.to_dict()

    assert status["enabled"] == True
    assert status["budget"]["calls_used"] == 0
    assert status["features"]["trade_rationale"]["calls"] == 2
    assert status["features"]["trade_rationale"]["successes"] == 1
    assert status["features"]["trade_rationale"]["success_rate"] == 0.5
    assert status["features"]["daily_journal"]["generated"] == True
    assert status["health"] == "healthy"


def test_status_snapshot_with_errors(mock_config):
    """Test status snapshot tracks errors."""
    client = CoPilotClient(mock_config)
    snapshot = StatusSnapshot(client, mock_config)

    snapshot.record_error("Test error 1")
    snapshot.record_error("Test error 2")

    status = snapshot.to_dict()

    assert len(status["errors"]) == 2
    assert status["health"] == "degraded"


def test_status_snapshot_persistence(mock_config, tmp_path, monkeypatch):
    """Test status snapshot writes to disk."""
    monkeypatch.chdir(tmp_path)

    client = CoPilotClient(mock_config)
    snapshot = StatusSnapshot(client, mock_config)

    success = snapshot.write_snapshot()

    assert success == True

    status_path = Path("logs/ai_copilot/latest_status.json")
    assert status_path.exists()

    # Load and verify
    loaded = load_latest_status()
    assert loaded is not None
    assert loaded["enabled"] == True


# ============================================================================
# Config Tests
# ============================================================================


def test_config_loading_with_ai_copilot():
    """Test config loads AI Co-Pilot settings from YAML."""
    from src.app.config import load_config_with_yaml

    config = load_config_with_yaml()

    # Verify AI Co-Pilot fields exist with defaults
    assert hasattr(config, "ai_copilot_enabled")
    assert hasattr(config, "ai_copilot_influence_decisions")
    assert hasattr(config, "ai_copilot_model")
    assert hasattr(config, "ai_copilot_max_calls_per_run")
    assert hasattr(config, "ai_copilot_trade_rationale_enabled")
    assert hasattr(config, "ai_copilot_daily_journal_enabled")
    assert hasattr(config, "ai_copilot_strategy_critique_enabled")

    # Verify safety defaults
    assert config.ai_copilot_enabled == False  # Default OFF
    assert config.ai_copilot_influence_decisions == False  # Default no influence


def test_config_env_var_override(monkeypatch):
    """Test AI_COPILOT_ENABLED env var overrides YAML."""
    from src.app.config import load_config_with_yaml

    # Set env var to enable
    monkeypatch.setenv("AI_COPILOT_ENABLED", "1")

    config = load_config_with_yaml()

    # Should be enabled by env var (regardless of YAML)
    assert config.ai_copilot_enabled == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
