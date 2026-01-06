"""Safety guardrails for proposal filtering."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import ProposalSet
from .storage import load_history


def apply_guardrails(
    proposal_set: ProposalSet,
    config: dict,  # Guardrails config
    history_file: Path,
) -> ProposalSet:
    """
    Apply safety guardrails to proposals.

    Filters out proposals that violate:
    - min_confidence threshold
    - expired TTL
    - max_sector_toggles_per_day
    - cooldown_days per sector

    Args:
        proposal_set: Generated proposals
        config: Guardrails configuration
        history_file: Path to history file

    Returns:
        Filtered proposal set
    """
    min_confidence = config.get("min_confidence", 0.70)
    max_toggles_per_day = config.get("max_sector_toggles_per_day", 1)
    cooldown_days = config.get("cooldown_days", 3)

    now = datetime.now(UTC)

    # Load history
    history = load_history(history_file)

    # Count recent toggles per sector
    cutoff_day = now - timedelta(days=1)

    toggles_today = {}
    last_toggle_by_sector = {}

    for entry in history:
        if entry.get("status") not in ["APPROVED", "APPLIED"]:
            continue

        timestamp_str = entry.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            continue

        sector = entry.get("sector_name")
        if not sector:
            continue

        # Count toggles today
        if timestamp >= cutoff_day:
            toggles_today[sector] = toggles_today.get(sector, 0) + 1

        # Track last toggle
        if sector not in last_toggle_by_sector or timestamp > datetime.fromisoformat(
            last_toggle_by_sector[sector]
        ):
            last_toggle_by_sector[sector] = timestamp.isoformat()

    # Filter proposals
    filtered_proposals = []

    for proposal in proposal_set.proposals:
        # Check confidence
        if proposal.confidence < min_confidence:
            print(
                f"FILTERED: {proposal.sector_name} - "
                f"confidence {proposal.confidence} < {min_confidence}"
            )
            continue

        # Check expiry
        try:
            expires = datetime.fromisoformat(proposal.expires_at)
            if now >= expires:
                print(f"FILTERED: {proposal.sector_name} - expired")
                continue
        except ValueError:
            pass

        # Check max toggles per day
        if toggles_today.get(proposal.sector_name, 0) >= max_toggles_per_day:
            print(f"FILTERED: {proposal.sector_name} - max toggles/day exceeded")
            continue

        # Check cooldown
        last_toggle_str = last_toggle_by_sector.get(proposal.sector_name)
        if last_toggle_str:
            try:
                last_toggle = datetime.fromisoformat(last_toggle_str)
                if now - last_toggle < timedelta(days=cooldown_days):
                    print(f"FILTERED: {proposal.sector_name} - cooldown active")
                    continue
            except ValueError:
                pass

        filtered_proposals.append(proposal)

    return ProposalSet(
        generation_id=proposal_set.generation_id,
        proposals=filtered_proposals,
        disagreements=proposal_set.disagreements,
        regime=proposal_set.regime,
        headline_count=proposal_set.headline_count,
        generated_at=proposal_set.generated_at,
    )
