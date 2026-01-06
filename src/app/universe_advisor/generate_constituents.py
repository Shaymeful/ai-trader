"""Generate constituent change proposals from candidates."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.app.llm.factory import get_providers_for_mode

from .models import (
    ConstituentChange,
    ConstituentChangeAction,
    Proposal,
    ProposalType,
    RegimeData,
)
from .storage import load_history


def load_recent_candidates(
    events_file: Path,
    lookback_hours: int = 24,
    max_candidates: int = 50,
) -> list[dict]:
    """Load recent candidate_created events from events.jsonl.

    Args:
        events_file: Path to events.jsonl file
        lookback_hours: Hours to look back
        max_candidates: Maximum candidates to return

    Returns:
        List of recent candidate events
    """
    if not events_file.exists():
        return []

    import json

    cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)
    candidates = []
    seen_tickers = set()

    with open(events_file, encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)

                if event.get("event_type") != "candidate_created":
                    continue

                timestamp_str = event.get("timestamp", "")
                timestamp = datetime.fromisoformat(timestamp_str.replace("-05:00", "+00:00"))

                if timestamp < cutoff:
                    continue

                ticker = event.get("symbol")
                if not ticker or ticker in seen_tickers:
                    continue

                seen_tickers.add(ticker)
                candidates.append(event)

            except (json.JSONDecodeError, ValueError):
                continue

    # Sort by confidence descending
    candidates.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    return candidates[:max_candidates]


def check_ticker_constraints(
    ticker: str,
    sector_name: str,
    sectors: dict[str, dict],
    config: dict,
    history_file: Path,
    broker_api=None,
) -> tuple[bool, dict[str, bool]]:
    """Check if ticker passes all constraints.

    Args:
        ticker: Ticker symbol to check
        sector_name: Target sector name
        sectors: Sector definitions
        config: Configuration dict with blacklist, cooldown, etc.
        history_file: History file path
        broker_api: Optional broker API for tradability check

    Returns:
        (passes, constraints_dict) where constraints_dict shows what was checked
    """
    constraints = {
        "not_blacklisted": True,
        "not_in_sector": True,
        "cooldown_ok": True,
        "tradable": True,
    }

    # Check blacklist
    blacklist = config.get("llm_ticker_blacklist", [])
    if ticker in blacklist:
        constraints["not_blacklisted"] = False
        return False, constraints

    # Check if already in sector
    sector_tickers = sectors.get(sector_name, {}).get("symbols", [])
    if ticker in sector_tickers:
        constraints["not_in_sector"] = False
        return False, constraints

    # Check cooldown
    cooldown_days = config.get("llm_cooldown_days_per_ticker", 7)
    cutoff = datetime.now(UTC) - timedelta(days=cooldown_days)

    history = load_history(history_file)
    for entry in history:
        if entry.get("proposal_type") != "constituent_change":
            continue

        constituent_change = entry.get("constituent_change")
        if not constituent_change:
            continue

        if ticker in constituent_change.get("tickers", []):
            timestamp_str = entry.get("timestamp", "")
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
                if timestamp >= cutoff:
                    constraints["cooldown_ok"] = False
                    return False, constraints
            except ValueError:
                pass

    # Check tradability (basic check - could be enhanced with broker API)
    if broker_api:
        # TODO: Add actual broker API call to check if tradable
        pass

    # All checks passed
    return True, constraints


def generate_constituent_proposals(
    config: dict,
    regime: RegimeData,
    candidates: list[dict],
    sectors: dict[str, dict],
    history_file: Path,
    ttl_minutes: int = 120,
) -> list[Proposal]:
    """Generate constituent change proposals from candidates.

    Args:
        config: Full config dict with LLM and constituent settings
        regime: Market regime data
        candidates: Recent candidates from selector
        sectors: Sector definitions
        history_file: History file path
        ttl_minutes: Proposal TTL in minutes

    Returns:
        List of constituent change proposals
    """
    # Check if constituent proposals are enabled
    if not config.get("llm_enable_constituent_proposals", True):
        return []

    # Get constraints
    max_add = config.get("llm_max_add_per_run", 2)
    min_confidence = config.get("llm_min_confidence_add", 0.80)

    # Filter candidates by confidence
    filtered_candidates = [c for c in candidates if c.get("confidence", 0) >= min_confidence]

    if not filtered_candidates:
        return []

    # Check constraints for each candidate
    viable_candidates = []
    for candidate in filtered_candidates:
        ticker = candidate.get("symbol")
        sector = candidate.get("sector")

        if not ticker or not sector:
            continue

        if sector not in sectors:
            continue

        passes, constraints_checked = check_ticker_constraints(
            ticker, sector, sectors, config, history_file
        )

        if passes:
            viable_candidates.append(
                {
                    "candidate": candidate,
                    "target_sector": sector,
                    "constraints_checked": constraints_checked,
                }
            )

    if not viable_candidates:
        return []

    # Limit to max_add
    viable_candidates = viable_candidates[:max_add]

    # Generate proposals using LLM for rationale
    mode = config.get("llm_mode", "openai_only")
    primary = config.get("llm_primary", "openai")

    providers = get_providers_for_mode(
        mode=mode,
        primary=primary,
        openai_model=config.get("llm_openai_model"),
        anthropic_model=config.get("llm_anthropic_model"),
        timeout=config.get("llm_timeout", 30),
    )

    provider = providers[0]  # Use first provider for constituent proposals

    # Build prompt for LLM
    prompt = _build_constituent_prompt(regime, viable_candidates, sectors)

    schema = {
        "proposals": [
            {
                "ticker": "string",
                "sector": "string",
                "confidence": "number",
                "rationale": "string",
                "supporting_headline_numbers": ["number"],
            }
        ]
    }

    try:
        response = provider.generate_structured_json(prompt, schema)
    except Exception as e:
        print(f"LLM call failed for constituent proposals: {e}")
        return []

    # Convert LLM responses to Proposal objects
    proposals = []
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=ttl_minutes)

    for prop_data in response.get("proposals", []):
        ticker = prop_data.get("ticker")
        sector = prop_data.get("sector")

        # Find the matching viable candidate
        matching = None
        for vc in viable_candidates:
            if vc["candidate"].get("symbol") == ticker:
                matching = vc
                break

        if not matching:
            continue

        # Extract supporting headlines
        headline_numbers = prop_data.get("supporting_headline_numbers", [])
        supporting_headlines = []
        if headline_numbers and len(headline_numbers) > 0:
            headline = matching["candidate"].get("headline", "")
            if headline:
                supporting_headlines.append(headline)

        # Create ConstituentChange object
        constituent_change = ConstituentChange(
            action=ConstituentChangeAction.ADD,
            tickers=[ticker],
            reason=prop_data.get("rationale", ""),
            constraints_checked=matching["constraints_checked"],
        )

        # Create Proposal
        proposal = Proposal(
            proposal_id=str(uuid.uuid4()),
            sector_name=sector,
            confidence=prop_data.get("confidence", min_confidence),
            rationale=prop_data.get("rationale", ""),
            supporting_headlines=supporting_headlines,
            provider=provider.get_provider_name(),
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            status="NEW",
            proposal_type=ProposalType.CONSTITUENT_CHANGE,
            recommended_enabled=None,
            constituent_change=constituent_change,
        )

        proposals.append(proposal)

    return proposals


def _build_constituent_prompt(
    regime: RegimeData,
    viable_candidates: list[dict],
    sectors: dict[str, dict],
) -> str:
    """Build prompt for LLM to generate constituent change rationales.

    Args:
        regime: Market regime data
        viable_candidates: List of viable candidates with constraints
        sectors: Sector definitions

    Returns:
        Prompt string for LLM
    """
    # Format regime
    regime_desc = f"""Current Market Regime: {regime.regime.value}
- SPY Price: ${regime.spy_price:.2f}
- SPY MA50: ${regime.spy_ma50:.2f}
- Trend: {regime.trend}
- Volatility: {regime.volatility} (annualized: {regime.volatility_value:.1%})"""

    # Format candidates
    candidates_desc = "\n\nCandidate Tickers:\n"
    for i, vc in enumerate(viable_candidates, 1):
        candidate = vc["candidate"]
        ticker = candidate.get("symbol")
        headline = candidate.get("headline", "")
        action = candidate.get("action", "")
        sector = vc["target_sector"]
        confidence = candidate.get("confidence", 0)

        candidates_desc += (
            f"{i}. {ticker} -> {sector} (confidence: {confidence:.2f})\n"
            f"   Action: {action}\n"
            f"   Headline: {headline}\n"
        )

    # Format sectors
    sectors_desc = "\n\nAvailable Sectors:\n"
    for name, data in sectors.items():
        symbols = ", ".join(data["symbols"][:5])
        if len(data["symbols"]) > 5:
            symbols += f" (+{len(data['symbols']) - 5} more)"
        sectors_desc += f"- {name}: {data['description']} ({symbols})\n"

    # Build prompt
    prompt = f"""{regime_desc}

{candidates_desc}

{sectors_desc}

Task: For each candidate ticker above, provide a rationale for adding it to the target sector.

Consider:
1. Does the ticker fit the sector theme?
2. Is the timing appropriate given the current market regime?
3. What is your confidence in this addition (0.0-1.0)?
4. Keep rationale concise (1-2 sentences)

Respond with JSON in this exact format:
{{
  "proposals": [
    {{
      "ticker": "ROK",
      "sector": "automation",
      "confidence": 0.85,
      "rationale": "Rockwell Automation is a core automation stock with strong earnings...",
      "supporting_headline_numbers": [1]
    }}
  ]
}}"""

    return prompt
