"""Proposal storage (JSON + JSONL)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from .models import Proposal, ProposalSet


def save_proposals(proposal_set: ProposalSet, file_path: Path) -> None:
    """Save proposals to JSON file (atomic write).
    
    Args:
        proposal_set: Proposals to save
        file_path: Path to JSON file
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "generation_id": proposal_set.generation_id,
        "generated_at": proposal_set.generated_at,
        "headline_count": proposal_set.headline_count,
        "regime": {
            "regime": proposal_set.regime.regime.value,
            "spy_price": proposal_set.regime.spy_price,
            "spy_ma50": proposal_set.regime.spy_ma50,
            "trend": proposal_set.regime.trend,
            "volatility": proposal_set.regime.volatility,
            "volatility_value": proposal_set.regime.volatility_value,
            "confidence": proposal_set.regime.confidence,
            "timestamp": proposal_set.regime.timestamp,
        },
        "proposals": [
            {
                "proposal_id": p.proposal_id,
                "sector_name": p.sector_name,
                "recommended_enabled": p.recommended_enabled,
                "confidence": p.confidence,
                "rationale": p.rationale,
                "supporting_headlines": p.supporting_headlines,
                "provider": p.provider,
                "created_at": p.created_at,
                "expires_at": p.expires_at,
                "status": p.status,
            }
            for p in proposal_set.proposals
        ],
        "disagreements": [
            {
                "disagreement_id": d.disagreement_id,
                "sector_name": d.sector_name,
                "provider_a": d.provider_a,
                "recommendation_a": d.recommendation_a,
                "confidence_a": d.confidence_a,
                "provider_b": d.provider_b,
                "recommendation_b": d.recommendation_b,
                "confidence_b": d.confidence_b,
                "created_at": d.created_at,
            }
            for d in proposal_set.disagreements
        ],
    }

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


def load_proposals(file_path: Path) -> dict | None:
    """Load proposals from JSON file.
    
    Args:
        file_path: Path to JSON file
        
    Returns:
        Proposals dict or None if file doesn't exist
    """
    if not file_path.exists():
        return None

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        return data

    except Exception as e:
        print(f"Failed to load proposals: {e}")
        return None


def append_to_history(
    proposal: Proposal,
    action: str,  # "APPROVED" or "REJECTED"
    history_file: Path,
) -> None:
    """Append proposal action to history file (append-only).
    
    Args:
        proposal: Proposal being acted upon
        action: Action taken (APPROVED or REJECTED)
        history_file: Path to history JSONL file
    """
    history_file.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
        "proposal_id": proposal.proposal_id,
        "sector_name": proposal.sector_name,
        "recommended_enabled": proposal.recommended_enabled,
        "confidence": proposal.confidence,
        "provider": proposal.provider,
        "status": action,
    }

    with open(history_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
