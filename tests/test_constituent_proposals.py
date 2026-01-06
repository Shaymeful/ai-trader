"""Test constituent change proposals."""

from datetime import UTC, datetime, timedelta

from src.app.universe_advisor.models import (
    ConstituentChange,
    ConstituentChangeAction,
    Proposal,
    ProposalType,
)
from src.app.universe_registry import UniverseRegistry


def test_constituent_change_dataclass():
    """Test ConstituentChange dataclass creation."""
    change = ConstituentChange(
        action=ConstituentChangeAction.ADD,
        tickers=["ROK", "ABB"],
        reason="Strong earnings in automation sector",
        constraints_checked={"tradable": True, "not_blacklisted": True},
    )

    assert change.action == ConstituentChangeAction.ADD
    assert len(change.tickers) == 2
    assert "ROK" in change.tickers


def test_constituent_proposal_creation():
    """Test creating a CONSTITUENT_CHANGE proposal."""
    constituent_change = ConstituentChange(
        action=ConstituentChangeAction.ADD,
        tickers=["ROK"],
        reason="Test reason",
        constraints_checked={"tradable": True},
    )

    proposal = Proposal(
        proposal_id="test-123",
        sector_name="automation",
        confidence=0.85,
        rationale="Test rationale",
        supporting_headlines=["Test headline"],
        provider="openai",
        created_at=datetime.now(UTC).isoformat(),
        expires_at=(datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        status="NEW",
        proposal_type=ProposalType.CONSTITUENT_CHANGE,
        recommended_enabled=None,
        constituent_change=constituent_change,
    )

    assert proposal.proposal_type == ProposalType.CONSTITUENT_CHANGE
    assert proposal.constituent_change is not None
    assert proposal.constituent_change.action == ConstituentChangeAction.ADD
    assert "ROK" in proposal.constituent_change.tickers


def test_registry_stage_constituent_add(tmp_path):
    """Test UniverseRegistry staging an ADD constituent change."""
    # Create test config
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
universe:
  sectors:
    test_sector:
      enabled: true
      description: "Test sector"
      symbols:
        - AAPL
        - MSFT
""")

    overrides_file = tmp_path / "overrides.json"

    registry = UniverseRegistry(
        base_config_path=config_file,
        overrides_path=overrides_file,
    )

    # Stage ADD of ROK to test_sector
    pending_version = registry.stage_constituent_change(
        "test_sector",
        "add",
        ["ROK", "ABB"],
    )

    assert pending_version == 1

    # Verify tickers were added in memory
    assert "ROK" in registry.sectors["test_sector"].symbols
    assert "ABB" in registry.sectors["test_sector"].symbols
    assert "AAPL" in registry.sectors["test_sector"].symbols  # Original still there

    # Verify overrides file was saved
    assert overrides_file.exists()


def test_registry_stage_constituent_remove(tmp_path):
    """Test UniverseRegistry staging a REMOVE constituent change."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
universe:
  sectors:
    test_sector:
      enabled: true
      description: "Test sector"
      symbols:
        - AAPL
        - MSFT
        - ROK
""")

    overrides_file = tmp_path / "overrides.json"

    registry = UniverseRegistry(
        base_config_path=config_file,
        overrides_path=overrides_file,
    )

    # Stage REMOVE of ROK from test_sector
    pending_version = registry.stage_constituent_change(
        "test_sector",
        "remove",
        ["ROK"],
    )

    assert pending_version == 1

    # Verify ticker was removed in memory
    assert "ROK" not in registry.sectors["test_sector"].symbols
    assert "AAPL" in registry.sectors["test_sector"].symbols  # Others still there
    assert "MSFT" in registry.sectors["test_sector"].symbols


def test_registry_activate_pending_constituent(tmp_path):
    """Test activating pending constituent changes."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
universe:
  sectors:
    test_sector:
      enabled: true
      description: "Test sector"
      symbols:
        - AAPL
""")

    overrides_file = tmp_path / "overrides.json"

    registry = UniverseRegistry(
        base_config_path=config_file,
        overrides_path=overrides_file,
    )

    # Stage change
    registry.stage_constituent_change("test_sector", "add", ["ROK"])

    # Verify pending
    assert registry.overrides["test_sector"].pending_version == 1
    assert registry.overrides["test_sector"].active_version == 0

    # Activate
    activated = registry.check_and_activate_pending()

    assert len(activated) == 1
    assert activated[0][0] == "test_sector"
    assert activated[0][1] == 0  # old version
    assert activated[0][2] == 1  # new version

    # Verify activated
    assert registry.overrides["test_sector"].active_version == 1
    assert registry.overrides["test_sector"].pending_version is None
