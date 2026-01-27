"""
Trade Rationale Advisor - AI-powered rationale for trading candidates.

Generates human-readable rationale explaining why a candidate is actionable,
including confidence, risk factors, and key considerations.

SAFETY:
- Advisory-only (does not affect trade execution unless config.ai_copilot_influence_decisions=True)
- Gracefully degrades on LLM failures
- Budget-gated via CoPilotClient
"""

import logging
from typing import Any

from src.app.candidates.schema import Candidate
from src.app.config import Config
from src.app.llm_advisors.client import CoPilotClient

logger = logging.getLogger("ai-trader.copilot.rationale")


class TradeRationaleResult:
    """Result from trade rationale generation."""

    def __init__(
        self,
        candidate_id: str,
        rationale: str | None = None,
        confidence: int | None = None,
        risk_factors: list[str] | None = None,
        success: bool = False,
    ):
        self.candidate_id = candidate_id
        self.rationale = rationale
        self.confidence = confidence  # 0-100
        self.risk_factors = risk_factors or []
        self.success = success

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "candidate_id": self.candidate_id,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "risk_factors": self.risk_factors,
            "success": self.success,
        }


def generate_trade_rationale(
    candidate: Candidate,
    client: CoPilotClient,
    config: Config,
    context: dict[str, Any] | None = None,
) -> TradeRationaleResult:
    """
    Generate AI rationale for a trading candidate.

    Args:
        candidate: Candidate to generate rationale for
        client: CoPilot client (budget-gated)
        config: Application configuration
        context: Optional context (current price, recent news, etc.)

    Returns:
        TradeRationaleResult with rationale or None on failure

    Safety:
        - Never raises exceptions
        - Returns unsuccessful result if disabled or failed
        - Respects budget gates via client
    """
    # Check if feature is enabled
    if not config.ai_copilot_trade_rationale_enabled:
        logger.debug(f"[{candidate.symbol}] Trade rationale disabled")
        return TradeRationaleResult(candidate.candidate_id, success=False)

    # Build context string
    context_str = _build_context_string(candidate, context)

    # Build prompt
    prompt = f"""You are an AI trading analyst. Analyze this trading candidate and provide a concise rationale.

CANDIDATE:
Symbol: {candidate.symbol}
Action: {candidate.action.value.upper()}
Confidence: {candidate.confidence:.1%}
Sector: {candidate.sector or "Unknown"}
Horizon: {candidate.horizon.value}
Event Type: {candidate.event_type or "N/A"}
Reason: {candidate.reason or "N/A"}

{context_str}

TASK:
Provide a clear, concise rationale for why this is a {candidate.action.value.upper()} opportunity right now.

Consider:
1. What makes this actionable NOW?
2. What are the key supporting factors?
3. What are the main risk factors to watch?
4. What is your confidence level (0-100)?

Be specific and actionable. Focus on the "why" and "what could go wrong".
"""

    # Define JSON schema for response
    schema = {
        "type": "object",
        "properties": {
            "rationale": {
                "type": "string",
                "description": "Clear, concise explanation (2-3 sentences)",
            },
            "confidence": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "AI confidence in this analysis (0-100)",
            },
            "risk_factors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of 1-3 key risk factors to monitor",
            },
        },
        "required": ["rationale", "confidence", "risk_factors"],
    }

    # Call LLM (budget-gated, with retries)
    result = client.generate_advisory_json(
        prompt=prompt,
        schema=schema,
        temperature=0.7,
        feature_name=f"trade_rationale.{candidate.symbol}",
    )

    if result is None:
        logger.warning(f"[{candidate.symbol}] Failed to generate rationale")
        return TradeRationaleResult(candidate.candidate_id, success=False)

    # Extract fields
    rationale = result.get("rationale")
    confidence = result.get("confidence")
    risk_factors = result.get("risk_factors", [])

    logger.info(
        f"[{candidate.symbol}] Generated rationale: confidence={confidence}, "
        f"risks={len(risk_factors)}"
    )

    return TradeRationaleResult(
        candidate_id=candidate.candidate_id,
        rationale=rationale,
        confidence=confidence,
        risk_factors=risk_factors,
        success=True,
    )


def _build_context_string(candidate: Candidate, context: dict[str, Any] | None) -> str:
    """Build context string from optional context dict."""
    if not context:
        return ""

    parts = []

    if "current_price" in context:
        parts.append(f"Current Price: ${context['current_price']:.2f}")

    if "price_change_pct" in context:
        parts.append(f"Price Change: {context['price_change_pct']:+.2f}%")

    if "volume" in context:
        parts.append(f"Volume: {context['volume']:,.0f}")

    if "recent_news" in context:
        news = context["recent_news"]
        if isinstance(news, list) and news:
            parts.append(f"Recent News: {', '.join(news[:3])}")
        elif isinstance(news, str):
            parts.append(f"Recent News: {news}")

    if "technical_signal" in context:
        parts.append(f"Technical Signal: {context['technical_signal']}")

    if parts:
        return "CONTEXT:\n" + "\n".join(parts) + "\n"
    return ""


def enrich_candidates_with_rationale(
    candidates: list[Candidate],
    client: CoPilotClient,
    config: Config,
    max_candidates: int = 5,
) -> dict[str, TradeRationaleResult]:
    """
    Enrich multiple candidates with AI rationale (respecting budget).

    Args:
        candidates: List of candidates to enrich
        client: CoPilot client
        config: Application configuration
        max_candidates: Maximum candidates to enrich (default 5)

    Returns:
        Dict mapping candidate_id -> TradeRationaleResult

    Safety:
        - Respects budget via client
        - Stops when budget exhausted
        - Never raises exceptions
    """
    results: dict[str, TradeRationaleResult] = {}

    # Filter to tradeable candidates only (BUY/SELL)
    tradeable = [c for c in candidates if c.is_tradeable()]

    # Sort by confidence (highest first) and take top N
    tradeable.sort(key=lambda c: c.confidence, reverse=True)
    top_candidates = tradeable[:max_candidates]

    logger.info(
        f"Enriching {len(top_candidates)} candidates with AI rationale "
        f"(budget: {client.get_remaining_budget()} calls)"
    )

    for candidate in top_candidates:
        # Check if budget exhausted
        if client.get_remaining_budget() <= 0:
            logger.warning("Budget exhausted, stopping rationale generation")
            break

        result = generate_trade_rationale(candidate, client, config)
        results[candidate.candidate_id] = result

    logger.info(
        f"Generated {sum(1 for r in results.values() if r.success)} successful rationales"
    )

    return results
