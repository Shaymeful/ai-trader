"""Apply approved proposals to UniverseRegistry."""

import json
from datetime import UTC, datetime
from pathlib import Path

from .models import Proposal
from .storage import append_to_history, load_proposals


def apply_proposal(
    proposal: Proposal,
    universe_registry,  # UniverseRegistry instance
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
    if proposal.proposal_type == "constituent_change" and proposal.constituent_change:
        # For constituent changes, add/remove tickers
        # Build rationales dict (same rationale for all tickers in this proposal)
        rationales = None
        if proposal.constituent_change.reason:
            rationales = {
                ticker: proposal.constituent_change.reason
                for ticker in proposal.constituent_change.tickers
            }

        new_version = universe_registry.stage_constituent_change(
            proposal.sector_name,
            proposal.constituent_change.action.value,
            proposal.constituent_change.tickers,
            rationales=rationales,
        )
    else:
        # For sector toggle, enable/disable sector
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
        save_proposals_dict(proposal_set, proposals_file)

    # Append to history
    append_to_history(proposal, "APPROVED", history_file)

    return new_version


def save_proposals_dict(data: dict, file_path: Path) -> None:
    """Save proposals dict to file (helper for apply_proposal).

    Args:
        data: Proposals dict
        file_path: Path to JSON file
    """
    from tempfile import NamedTemporaryFile

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
    for p in proposal_set.get("proposals", []):
        if p["sector_name"] == sector_name and p["status"] == "APPROVED":
            p["status"] = "APPLIED"

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

    # Save updated proposals
    save_proposals_dict(proposal_set, proposals_file)
