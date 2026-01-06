"""Apply approved proposals by staging UniverseRegistry changes."""

import json
from datetime import UTC, datetime
from pathlib import Path

from src.app.universe_registry import UniverseRegistry

from .models import Proposal
from .storage import append_to_history, load_proposals, save_proposals


def apply_proposal(
    proposal: Proposal,
    universe_registry: UniverseRegistry,
    proposals_file: Path,
    history_file: Path,
) -> int:
    """
    Apply approved proposal by staging UniverseRegistry change.

    Args:
        proposal: Approved proposal
        universe_registry: Universe registry instance
        proposals_file: Path to proposals JSON
        history_file: Path to history JSONL

    Returns:
        New pending_version from registry
    """
    # Stage change in UniverseRegistry
    new_version = universe_registry.stage_change(
        proposal.sector_name,
        proposal.recommended_enabled,
    )

    # Update proposal status to APPROVED
    proposal.status = "APPROVED"

    # Save updated proposals
    proposal_set = load_proposals(proposals_file)
    if proposal_set:
        # Update the specific proposal
        for p in proposal_set["proposals"]:
            if p["proposal_id"] == proposal.proposal_id:
                p["status"] = "APPROVED"

        # Re-save (atomic write)
        from .models import Disagreement, MarketRegime, ProposalSet, RegimeData

        # Reconstruct ProposalSet for save
        regime_data = proposal_set.get("regime", {})
        regime = RegimeData(
            regime=MarketRegime(regime_data.get("regime", "unknown")),
            spy_price=regime_data.get("spy_price", 0.0),
            spy_ma50=regime_data.get("spy_ma50", 0.0),
            trend=regime_data.get("trend", "bear"),
            volatility=regime_data.get("volatility", "high"),
            volatility_value=regime_data.get("volatility_value", 0.0),
            confidence=regime_data.get("confidence", 0.0),
            timestamp=regime_data.get("timestamp", datetime.now(UTC).isoformat()),
        )

        proposals_list = [Proposal(**p) for p in proposal_set.get("proposals", [])]
        disagreements_list = [Disagreement(**d) for d in proposal_set.get("disagreements", [])]

        updated_set = ProposalSet(
            generation_id=proposal_set.get("generation_id", ""),
            proposals=proposals_list,
            disagreements=disagreements_list,
            regime=regime,
            headline_count=proposal_set.get("headline_count", 0),
            generated_at=proposal_set.get("generated_at", datetime.now(UTC).isoformat()),
        )

        save_proposals(updated_set, proposals_file)

    # Append to history
    append_to_history(proposal, "APPROVED", history_file)

    return new_version


def mark_applied(
    sector_name: str,
    proposals_file: Path,
    history_file: Path,
) -> None:
    """
    Mark approved proposals as APPLIED after registry activation.

    Called by runner after universe_registry.check_and_activate_pending().

    Args:
        sector_name: Sector that was activated
        proposals_file: Path to proposals JSON
        history_file: Path to history JSONL
    """
    proposal_set = load_proposals(proposals_file)
    if not proposal_set:
        return

    # Find APPROVED proposals for this sector
    updated = False
    for p in proposal_set.get("proposals", []):
        if p["sector_name"] == sector_name and p["status"] == "APPROVED":
            p["status"] = "APPLIED"
            updated = True

            # Append to history
            history_entry = {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": "APPLIED",
                "proposal_id": p["proposal_id"],
                "sector_name": p["sector_name"],
                "recommended_enabled": p["recommended_enabled"],
                "confidence": p["confidence"],
                "provider": p["provider"],
                "status": "APPLIED",
            }

            with open(history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(history_entry) + "\n")

    # Save updated proposals if any changes
    if updated:
        from .models import Disagreement, MarketRegime, Proposal, ProposalSet, RegimeData

        regime_data = proposal_set.get("regime", {})
        regime = RegimeData(
            regime=MarketRegime(regime_data.get("regime", "unknown")),
            spy_price=regime_data.get("spy_price", 0.0),
            spy_ma50=regime_data.get("spy_ma50", 0.0),
            trend=regime_data.get("trend", "bear"),
            volatility=regime_data.get("volatility", "high"),
            volatility_value=regime_data.get("volatility_value", 0.0),
            confidence=regime_data.get("confidence", 0.0),
            timestamp=regime_data.get("timestamp", datetime.now(UTC).isoformat()),
        )

        proposals_list = [Proposal(**p) for p in proposal_set.get("proposals", [])]
        disagreements_list = [Disagreement(**d) for d in proposal_set.get("disagreements", [])]

        updated_set = ProposalSet(
            generation_id=proposal_set.get("generation_id", ""),
            proposals=proposals_list,
            disagreements=disagreements_list,
            regime=regime,
            headline_count=proposal_set.get("headline_count", 0),
            generated_at=proposal_set.get("generated_at", datetime.now(UTC).isoformat()),
        )

        save_proposals(updated_set, proposals_file)
