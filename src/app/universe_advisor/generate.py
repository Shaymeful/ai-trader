"""Proposal generation from LLMs using RSS events and market regime."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.app.llm.factory import get_providers_for_mode

from .models import Disagreement, Proposal, ProposalSet, RegimeData


def load_recent_rss_events(
    events_file: Path,
    lookback_hours: int = 24,
    max_headlines: int = 100,
) -> list[dict]:
    """
    Load recent RSS events from events.jsonl.

    Args:
        events_file: Path to out/selector/events.jsonl
        lookback_hours: How far back to look (default 24)
        max_headlines: Hard cap on headlines (default 100)

    Returns:
        List of event dicts with deduplication + prioritization
    """
    if not events_file.exists():
        return []

    cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)

    # Load and filter events
    recent_events = []
    seen_headlines = set()

    with open(events_file, encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)

                # Only include candidate_created or headline_processed
                event_type = event.get("event_type")
                if event_type not in ["candidate_created", "headline_processed"]:
                    continue

                # Parse timestamp
                timestamp_str = event.get("timestamp", "")
                timestamp = datetime.fromisoformat(timestamp_str)

                # Filter by recency
                if timestamp < cutoff:
                    continue

                # Dedupe by headline text
                headline = event.get("headline", "")
                if headline in seen_headlines:
                    continue

                seen_headlines.add(headline)
                recent_events.append(event)

            except (json.JSONDecodeError, ValueError):
                continue

    # Prioritize by:
    # 1. candidate_created (higher priority than headline_processed)
    # 2. confidence (if available)
    # 3. recency
    def priority_key(event):
        is_candidate = event.get("event_type") == "candidate_created"
        confidence = event.get("confidence", 0.5)
        timestamp_str = event.get("timestamp", "")
        return (is_candidate, confidence, timestamp_str)

    recent_events.sort(key=priority_key, reverse=True)

    # Apply hard cap
    return recent_events[:max_headlines]


def build_prompt(
    regime: RegimeData,
    events: list[dict],
    sectors: dict[str, dict],  # sector_name -> {description, symbols}
) -> str:
    """Build prompt for LLM.

    Args:
        regime: Market regime data
        events: Recent RSS events
        sectors: Sector definitions

    Returns:
        Formatted prompt string
    """
    # Format regime
    regime_desc = f"""Current Market Regime: {regime.regime.value}
- SPY Price: ${regime.spy_price:.2f}
- SPY MA50: ${regime.spy_ma50:.2f}
- Trend: {regime.trend}
- Volatility: {regime.volatility} (annualized: {regime.volatility_value:.1%})"""

    # Format headlines
    headlines_desc = f"\n\nRecent News Headlines ({len(events)} total):\n"
    for i, event in enumerate(events[:50], 1):  # Show top 50 in prompt
        headline = event.get("headline", "")
        symbol = event.get("symbol", "N/A")
        action = event.get("action", "N/A")
        headlines_desc += f"{i}. [{symbol}] {headline} (action: {action})\n"

    # Format sectors
    sectors_desc = "\n\nAvailable Sectors:\n"
    for name, data in sectors.items():
        symbols = ", ".join(data["symbols"][:5])  # Show first 5 symbols
        if len(data["symbols"]) > 5:
            symbols += f" (+{len(data['symbols']) - 5} more)"
        sectors_desc += f"- {name}: {data['description']} ({symbols})\n"

    # Build prompt
    prompt = f"""{regime_desc}

{headlines_desc}

{sectors_desc}

Task: Analyze the market regime and recent news to recommend which sectors should be enabled or disabled for trading.

For each sector, determine:
1. Should it be enabled (true) or disabled (false)?
2. Confidence level (0.0-1.0)
3. Rationale (1-2 sentences)
4. Supporting headlines (list of 3-5 most relevant headlines by number)

Guidelines:
- Be conservative: only recommend changes with high confidence (>0.70)
- Consider sector exposure to current market conditions
- Use news sentiment as signal but avoid overreacting to single headlines
- Diversification: don't disable all sectors unless extreme conditions

Respond with JSON in this exact format:
{{
  "proposals": [
    {{
      "sector_name": "mega_cap_tech",
      "recommended_enabled": true,
      "confidence": 0.85,
      "rationale": "Tech sector showing strength...",
      "supporting_headline_numbers": [1, 5, 12]
    }}
  ]
}}"""

    return prompt


def generate_proposals(
    config: dict,  # LLM config section
    regime: RegimeData,
    events: list[dict],
    sectors: dict[str, dict],
    ttl_minutes: int = 120,
) -> ProposalSet:
    """
    Generate proposals using configured LLM provider(s).

    Args:
        config: LLM configuration dict
        regime: Market regime data
        events: Recent RSS events
        sectors: Sector definitions
        ttl_minutes: Proposal time-to-live

    Returns:
        ProposalSet with proposals and disagreements
    """
    mode = config.get("mode", "primary_fallback")
    primary = config.get("primary", "openai")

    providers = get_providers_for_mode(
        mode=mode,
        primary=primary,
        openai_model=config.get("openai_model"),
        anthropic_model=config.get("anthropic_model"),
        timeout=config.get("timeout", 30),
    )

    prompt = build_prompt(regime, events, sectors)
    schema = {
        "proposals": [
            {
                "sector_name": "string",
                "recommended_enabled": "boolean",
                "confidence": "number",
                "rationale": "string",
                "supporting_headline_numbers": ["number"],
            }
        ]
    }

    generation_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=ttl_minutes)

    proposals = []
    disagreements = []

    if mode in ["openai_only", "anthropic_only"]:
        # Single provider
        provider = providers[0]
        response = provider.generate_structured_json(prompt, schema)

        for prop_data in response.get("proposals", []):
            proposals.append(
                _create_proposal(prop_data, events, provider.get_provider_name(), now, expires_at)
            )

    elif mode == "primary_fallback":
        # Try primary, fallback to secondary
        primary_provider, fallback_provider = providers

        try:
            response = primary_provider.generate_structured_json(prompt, schema)
            provider_name = primary_provider.get_provider_name()
        except Exception as e:
            print(f"Primary provider failed: {e}, falling back...")
            response = fallback_provider.generate_structured_json(prompt, schema)
            provider_name = fallback_provider.get_provider_name()

        for prop_data in response.get("proposals", []):
            proposals.append(_create_proposal(prop_data, events, provider_name, now, expires_at))

    elif mode == "ensemble":
        # Call both providers
        openai_provider, anthropic_provider = providers

        openai_response = openai_provider.generate_structured_json(prompt, schema)
        anthropic_response = anthropic_provider.generate_structured_json(prompt, schema)

        # Merge with consensus logic
        proposals, disagreements = _merge_ensemble_responses(
            openai_response, anthropic_response, events, now, expires_at
        )

    return ProposalSet(
        generation_id=generation_id,
        proposals=proposals,
        disagreements=disagreements,
        regime=regime,
        headline_count=len(events),
        generated_at=now.isoformat(),
    )


def _create_proposal(
    prop_data: dict,
    events: list[dict],
    provider: str,
    now: datetime,
    expires_at: datetime,
) -> Proposal:
    """Helper to create Proposal from LLM response.

    Args:
        prop_data: Proposal data from LLM
        events: RSS events list
        provider: Provider name
        now: Current timestamp
        expires_at: Expiration timestamp

    Returns:
        Proposal instance
    """
    # Extract supporting headlines
    headline_numbers = prop_data.get("supporting_headline_numbers", [])
    supporting_headlines = []
    for num in headline_numbers[:5]:  # Cap at 5
        if 1 <= num <= len(events):
            headline = events[num - 1].get("headline", "")
            if headline:
                supporting_headlines.append(headline)

    return Proposal(
        proposal_id=str(uuid.uuid4()),
        sector_name=prop_data["sector_name"],
        recommended_enabled=prop_data["recommended_enabled"],
        confidence=prop_data["confidence"],
        rationale=prop_data["rationale"],
        supporting_headlines=supporting_headlines,
        provider=provider,
        created_at=now.isoformat(),
        expires_at=expires_at.isoformat(),
        status="NEW",
    )


def _merge_ensemble_responses(
    openai_response: dict,
    anthropic_response: dict,
    events: list[dict],
    now: datetime,
    expires_at: datetime,
) -> tuple[list[Proposal], list[Disagreement]]:
    """
    Merge responses from ensemble mode.

    Logic:
    - If both agree on direction → create proposal with "ensemble" provider
    - If they contradict → record as disagreement, drop proposal
    - If only one provider mentions a sector → use that recommendation

    Args:
        openai_response: OpenAI response dict
        anthropic_response: Anthropic response dict
        events: RSS events list
        now: Current timestamp
        expires_at: Expiration timestamp

    Returns:
        Tuple of (proposals, disagreements)
    """
    openai_props = {p["sector_name"]: p for p in openai_response.get("proposals", [])}
    anthropic_props = {p["sector_name"]: p for p in anthropic_response.get("proposals", [])}

    all_sectors = set(openai_props.keys()) | set(anthropic_props.keys())

    proposals = []
    disagreements = []

    for sector in all_sectors:
        openai_prop = openai_props.get(sector)
        anthropic_prop = anthropic_props.get(sector)

        if openai_prop and anthropic_prop:
            # Both mentioned this sector
            if openai_prop["recommended_enabled"] == anthropic_prop["recommended_enabled"]:
                # Agreement → create ensemble proposal
                avg_confidence = (openai_prop["confidence"] + anthropic_prop["confidence"]) / 2
                rationale_combined = (
                    f"OpenAI: {openai_prop['rationale']} | Claude: {anthropic_prop['rationale']}"
                )

                proposals.append(
                    Proposal(
                        proposal_id=str(uuid.uuid4()),
                        sector_name=sector,
                        recommended_enabled=openai_prop["recommended_enabled"],
                        confidence=avg_confidence,
                        rationale=rationale_combined,
                        supporting_headlines=_combine_headlines(
                            openai_prop, anthropic_prop, events
                        ),
                        provider="ensemble",
                        created_at=now.isoformat(),
                        expires_at=expires_at.isoformat(),
                        status="NEW",
                    )
                )
            else:
                # Contradiction → record disagreement
                disagreements.append(
                    Disagreement(
                        disagreement_id=str(uuid.uuid4()),
                        sector_name=sector,
                        provider_a="openai",
                        recommendation_a=openai_prop["recommended_enabled"],
                        confidence_a=openai_prop["confidence"],
                        provider_b="anthropic",
                        recommendation_b=anthropic_prop["recommended_enabled"],
                        confidence_b=anthropic_prop["confidence"],
                        created_at=now.isoformat(),
                    )
                )

        elif openai_prop:
            # Only OpenAI mentioned
            proposals.append(_create_proposal(openai_prop, events, "openai", now, expires_at))

        elif anthropic_prop:
            # Only Anthropic mentioned
            proposals.append(_create_proposal(anthropic_prop, events, "anthropic", now, expires_at))

    return proposals, disagreements


def _combine_headlines(
    openai_prop: dict,
    anthropic_prop: dict,
    events: list[dict],
) -> list[str]:
    """Combine supporting headlines from both providers.

    Args:
        openai_prop: OpenAI proposal data
        anthropic_prop: Anthropic proposal data
        events: RSS events list

    Returns:
        Combined list of headlines
    """
    numbers = set(openai_prop.get("supporting_headline_numbers", []))
    numbers.update(anthropic_prop.get("supporting_headline_numbers", []))

    headlines = []
    for num in sorted(numbers)[:5]:  # Cap at 5
        if 1 <= num <= len(events):
            headline = events[num - 1].get("headline", "")
            if headline and headline not in headlines:
                headlines.append(headline)

    return headlines
