"""Tests for Universe Advisor module."""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.app.universe_advisor.generate import (
    _combine_headlines,
    _create_proposal,
    _merge_ensemble_responses,
    generate_proposals,
    load_recent_rss_events,
)
from src.app.universe_advisor.guardrails import apply_guardrails
from src.app.universe_advisor.models import (
    MarketRegime,
    Proposal,
    ProposalSet,
    RegimeData,
)
from src.app.universe_advisor.storage import (
    append_to_history,
    load_history,
    load_proposals,
    save_proposals,
)
from tests.mocks.mock_llm_provider import MockLLMProvider


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_regime():
    """Sample market regime data."""
    return RegimeData(
        regime=MarketRegime.BULL_LOW_VOL,
        spy_price=450.0,
        spy_ma50=440.0,
        trend="bull",
        volatility="low",
        volatility_value=0.12,
        confidence=0.9,
        timestamp=datetime.now(UTC).isoformat(),
    )


@pytest.fixture
def sample_events():
    """Sample RSS events."""
    now = datetime.now(UTC)
    return [
        {
            "event_type": "candidate_created",
            "timestamp": now.isoformat(),
            "headline": "Tech stocks rally on earnings",
            "symbol": "AAPL",
            "action": "buy",
            "confidence": 0.85,
        },
        {
            "event_type": "headline_processed",
            "timestamp": (now - timedelta(hours=2)).isoformat(),
            "headline": "Energy sector faces headwinds",
            "symbol": "XLE",
            "action": "sell",
            "confidence": 0.75,
        },
    ]


@pytest.fixture
def sample_sectors():
    """Sample sector definitions."""
    return {
        "mega_cap_tech": {
            "description": "Tech stocks",
            "symbols": ["AAPL", "MSFT", "NVDA"],
        },
        "us_sector_etfs": {
            "description": "Sector ETFs",
            "symbols": ["XLF", "XLE"],
        },
    }


def test_load_recent_rss_events_no_file(temp_dir):
    """Test loading events when file doesn't exist."""
    events_file = temp_dir / "events.jsonl"
    events = load_recent_rss_events(events_file)
    assert events == []


def test_load_recent_rss_events_with_filter(temp_dir, sample_events):
    """Test loading events with filtering."""
    events_file = temp_dir / "events.jsonl"

    # Write events
    with open(events_file, "w", encoding="utf-8") as f:
        for event in sample_events:
            f.write(json.dumps(event) + "\n")

    # Load with 24h lookback
    events = load_recent_rss_events(events_file, lookback_hours=24)
    assert len(events) == 2


def test_load_recent_rss_events_deduplication(temp_dir):
    """Test headline deduplication."""
    events_file = temp_dir / "events.jsonl"
    now = datetime.now(UTC)

    # Write duplicate headlines
    events = [
        {
            "event_type": "candidate_created",
            "timestamp": now.isoformat(),
            "headline": "Same headline",
            "symbol": "AAPL",
        },
        {
            "event_type": "candidate_created",
            "timestamp": now.isoformat(),
            "headline": "Same headline",  # Duplicate
            "symbol": "MSFT",
        },
    ]

    with open(events_file, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")

    loaded = load_recent_rss_events(events_file)
    assert len(loaded) == 1


def test_create_proposal(sample_events):
    """Test proposal creation from LLM response."""
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=120)

    prop_data = {
        "sector_name": "mega_cap_tech",
        "recommended_enabled": True,
        "confidence": 0.85,
        "rationale": "Test rationale",
        "supporting_headline_numbers": [1, 2],
    }

    proposal = _create_proposal(prop_data, sample_events, "openai", now, expires_at)

    assert proposal.sector_name == "mega_cap_tech"
    assert proposal.recommended_enabled is True
    assert proposal.confidence == 0.85
    assert proposal.provider == "openai"
    assert proposal.status == "NEW"
    assert len(proposal.supporting_headlines) == 2


def test_merge_ensemble_responses_agreement(sample_events):
    """Test ensemble merge when providers agree."""
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=120)

    openai_response = {
        "proposals": [
            {
                "sector_name": "mega_cap_tech",
                "recommended_enabled": True,
                "confidence": 0.85,
                "rationale": "OpenAI rationale",
                "supporting_headline_numbers": [1],
            }
        ]
    }

    anthropic_response = {
        "proposals": [
            {
                "sector_name": "mega_cap_tech",
                "recommended_enabled": True,  # Agreement
                "confidence": 0.90,
                "rationale": "Anthropic rationale",
                "supporting_headline_numbers": [2],
            }
        ]
    }

    proposals, disagreements = _merge_ensemble_responses(
        openai_response, anthropic_response, sample_events, now, expires_at
    )

    assert len(proposals) == 1
    assert len(disagreements) == 0
    assert proposals[0].provider == "ensemble"
    assert proposals[0].confidence == 0.875  # Average


def test_merge_ensemble_responses_contradiction(sample_events):
    """Test ensemble merge when providers contradict."""
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=120)

    openai_response = {
        "proposals": [
            {
                "sector_name": "mega_cap_tech",
                "recommended_enabled": True,
                "confidence": 0.85,
                "rationale": "Enable tech",
                "supporting_headline_numbers": [1],
            }
        ]
    }

    anthropic_response = {
        "proposals": [
            {
                "sector_name": "mega_cap_tech",
                "recommended_enabled": False,  # Contradiction
                "confidence": 0.80,
                "rationale": "Disable tech",
                "supporting_headline_numbers": [2],
            }
        ]
    }

    proposals, disagreements = _merge_ensemble_responses(
        openai_response, anthropic_response, sample_events, now, expires_at
    )

    assert len(proposals) == 0  # Dropped due to contradiction
    assert len(disagreements) == 1
    assert disagreements[0].sector_name == "mega_cap_tech"


def test_merge_ensemble_responses_single_provider(sample_events):
    """Test ensemble merge when only one provider mentions a sector."""
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=120)

    openai_response = {
        "proposals": [
            {
                "sector_name": "mega_cap_tech",
                "recommended_enabled": True,
                "confidence": 0.85,
                "rationale": "Enable tech",
                "supporting_headline_numbers": [1],
            }
        ]
    }

    anthropic_response = {"proposals": []}  # No proposals

    proposals, disagreements = _merge_ensemble_responses(
        openai_response, anthropic_response, sample_events, now, expires_at
    )

    assert len(proposals) == 1
    assert len(disagreements) == 0
    assert proposals[0].provider == "openai"


def test_generate_proposals_openai_only(sample_regime, sample_events, sample_sectors):
    """Test proposal generation with openai_only mode."""
    mock_provider = MockLLMProvider("openai")

    # Mock factory to return our mock provider
    def mock_get_providers(mode, primary, **kwargs):
        return (mock_provider,)

    import src.app.universe_advisor.generate as gen_module

    original_get_providers = gen_module.get_providers_for_mode
    gen_module.get_providers_for_mode = mock_get_providers

    try:
        config = {
            "mode": "openai_only",
            "primary": "openai",
            "openai_model": "gpt-4",
            "timeout": 30,
        }

        proposal_set = generate_proposals(config, sample_regime, sample_events, sample_sectors)

        assert len(proposal_set.proposals) == 1
        assert proposal_set.proposals[0].provider == "openai"
        assert mock_provider.call_count == 1
    finally:
        gen_module.get_providers_for_mode = original_get_providers


def test_apply_guardrails_confidence_filter(temp_dir, sample_regime):
    """Test guardrails filter by confidence."""
    now = datetime.now(UTC)
    proposals = [
        Proposal(
            proposal_id="1",
            sector_name="test",
            recommended_enabled=True,
            confidence=0.60,  # Below threshold
            rationale="Low confidence",
            supporting_headlines=[],
            provider="test",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(hours=2)).isoformat(),
            status="NEW",
        )
    ]

    proposal_set = ProposalSet(
        generation_id="test",
        proposals=proposals,
        disagreements=[],
        regime=sample_regime,
        headline_count=10,
        generated_at=now.isoformat(),
    )

    guardrails_config = {
        "min_confidence": 0.70,
        "max_sector_toggles_per_day": 1,
        "cooldown_days": 3,
    }

    history_file = temp_dir / "history.jsonl"
    filtered_set = apply_guardrails(proposal_set, guardrails_config, history_file)

    assert len(filtered_set.proposals) == 0  # Filtered out


def test_apply_guardrails_cooldown(temp_dir, sample_regime):
    """Test guardrails enforce cooldown period."""
    now = datetime.now(UTC)

    # Create history with recent toggle
    history_file = temp_dir / "history.jsonl"
    recent_entry = {
        "timestamp": (now - timedelta(days=1)).isoformat(),
        "status": "APPROVED",
        "sector_name": "test_sector",
    }
    with open(history_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(recent_entry) + "\n")

    proposals = [
        Proposal(
            proposal_id="1",
            sector_name="test_sector",
            recommended_enabled=False,
            confidence=0.85,
            rationale="Test",
            supporting_headlines=[],
            provider="test",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(hours=2)).isoformat(),
            status="NEW",
        )
    ]

    proposal_set = ProposalSet(
        generation_id="test",
        proposals=proposals,
        disagreements=[],
        regime=sample_regime,
        headline_count=10,
        generated_at=now.isoformat(),
    )

    guardrails_config = {
        "min_confidence": 0.70,
        "max_sector_toggles_per_day": 1,
        "cooldown_days": 3,
    }

    filtered_set = apply_guardrails(proposal_set, guardrails_config, history_file)

    assert len(filtered_set.proposals) == 0  # Filtered due to cooldown


def test_save_and_load_proposals(temp_dir, sample_regime):
    """Test proposal persistence."""
    now = datetime.now(UTC)
    proposals = [
        Proposal(
            proposal_id="test-id",
            sector_name="test",
            recommended_enabled=True,
            confidence=0.85,
            rationale="Test",
            supporting_headlines=["Headline 1"],
            provider="test",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(hours=2)).isoformat(),
            status="NEW",
        )
    ]

    proposal_set = ProposalSet(
        generation_id="gen-1",
        proposals=proposals,
        disagreements=[],
        regime=sample_regime,
        headline_count=5,
        generated_at=now.isoformat(),
    )

    proposals_file = temp_dir / "proposals.json"
    save_proposals(proposal_set, proposals_file)

    # Load and verify
    loaded = load_proposals(proposals_file)
    assert loaded is not None
    assert loaded["generation_id"] == "gen-1"
    assert len(loaded["proposals"]) == 1
    assert loaded["proposals"][0]["sector_name"] == "test"


def test_append_to_history(temp_dir):
    """Test history file append."""
    now = datetime.now(UTC)
    proposal = Proposal(
        proposal_id="test-id",
        sector_name="test",
        recommended_enabled=True,
        confidence=0.85,
        rationale="Test",
        supporting_headlines=[],
        provider="test",
        created_at=now.isoformat(),
        expires_at=(now + timedelta(hours=2)).isoformat(),
        status="NEW",
    )

    history_file = temp_dir / "history.jsonl"
    append_to_history(proposal, "APPROVED", history_file)

    # Load and verify
    history = load_history(history_file)
    assert len(history) == 1
    assert history[0]["status"] == "APPROVED"
    assert history[0]["sector_name"] == "test"


def test_combine_headlines(sample_events):
    """Test headline combination from both providers."""
    openai_prop = {"supporting_headline_numbers": [1, 2]}
    anthropic_prop = {"supporting_headline_numbers": [2, 3]}

    headlines = _combine_headlines(openai_prop, anthropic_prop, sample_events)

    assert len(headlines) == 2  # Deduplicated
    assert headlines[0] == "Tech stocks rally on earnings"
