"""Apply approved proposals by staging UniverseRegistry changes."""

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from src.app.universe_registry import UniverseRegistry

from .models import Proposal, ProposalType
from .storage import append_to_history, load_proposals


def _save_proposals_dict(data: dict, file_path: Path) -> None:
    """Save proposals dict to JSON file with atomic write.

    Args:
        data: Proposals dict to save
        file_path: Destination file path
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=file_path.parent,
        delete=False,
        suffix=".tmp",
    ) as tmp_file:
        json.dump(data, tmp_file, indent=2)
        tmp_path = Path(tmp_file.name)

    tmp_path.replace(file_path)


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
    # Stage change in UniverseRegistry based on proposal type
    if proposal.proposal_type == ProposalType.SECTOR_TOGGLE:
        new_version = universe_registry.stage_change(
            proposal.sector_name,
            proposal.recommended_enabled,
        )
    elif proposal.proposal_type == ProposalType.CONSTITUENT_CHANGE:
        if not proposal.constituent_change:
            raise ValueError("CONSTITUENT_CHANGE proposal missing constituent_change data")
        new_version = universe_registry.stage_constituent_change(
            proposal.sector_name,
            proposal.constituent_change.action.value,
            proposal.constituent_change.tickers,
        )
    else:
        raise ValueError(f"Unknown proposal type: {proposal.proposal_type}")

    # Update proposal status to APPROVED
    proposal.status = "APPROVED"

    # Save updated proposals
    proposal_set = load_proposals(proposals_file)
    if proposal_set:
        # Update the specific proposal
        for p in proposal_set["proposals"]:
            if p["proposal_id"] == proposal.proposal_id:
                p["status"] = "APPROVED"

        # Save directly as dict (atomic write)
        _save_proposals_dict(proposal_set, proposals_file)

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
                "confidence": p["confidence"],
                "provider": p["provider"],
                "status": "APPLIED",
                "proposal_type": p.get("proposal_type", "sector_toggle"),
            }

            # Add type-specific fields
            if p.get("proposal_type") == "sector_toggle" or "recommended_enabled" in p:
                history_entry["recommended_enabled"] = p.get("recommended_enabled")
            if p.get("proposal_type") == "constituent_change" and "constituent_change" in p:
                history_entry["constituent_change"] = p["constituent_change"]

            with open(history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(history_entry) + "\n")

    # Save updated proposals if any changes
    if updated:
        _save_proposals_dict(proposal_set, proposals_file)
