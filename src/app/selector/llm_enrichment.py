"""LLM-based enrichment for candidate validation and classification."""

from __future__ import annotations

from typing import Any

from src.app.llm.factory import create_provider


class CandidateEnricher:
    """Enriches candidates using LLM for classification and validation."""

    def __init__(
        self,
        provider_type: str = "openai",
        model: str = "gpt-4o-mini",
        min_confidence: float = 0.70,
        timeout: int = 30,
    ):
        """
        Initialize enricher.

        Args:
            provider_type: LLM provider (openai or anthropic)
            model: Model name
            min_confidence: Minimum confidence threshold
            timeout: API timeout in seconds
        """
        self.provider = create_provider(provider_type, model=model, timeout=timeout)
        self.min_confidence = min_confidence
        self.model = model

    def enrich_candidates(
        self,
        candidates: list[dict[str, Any]],
        market_context: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """
        Enrich candidates with LLM classification.

        Args:
            candidates: List of raw candidates with ticker + reason
            market_context: Optional market regime/trend context

        Returns:
            (enriched_candidates, stats_dict)
        """
        if not candidates:
            return [], {"llm_called": False, "total_input": 0, "total_output": 0}

        # Build prompt
        prompt = self._build_prompt(candidates, market_context)

        # Expected schema
        schema = {
            "candidates": [
                {
                    "ticker": "string",
                    "action": "string",  # BUY, SELL, WATCH, IGNORE
                    "confidence": "number",  # 0.0-1.0
                    "sector": "string",
                    "rationale": "string",  # <= 200 chars
                }
            ]
        }

        try:
            # Call LLM
            response = self.provider.generate_structured_json(
                prompt=prompt,
                schema=schema,
                temperature=0.3,  # Lower temp for more consistent output
                max_tokens=2000,
            )

            # Parse response
            enriched = self._parse_response(response, candidates)

            stats = {
                "llm_called": True,
                "total_input": len(candidates),
                "total_output": len(enriched),
                "ignored": len(candidates) - len(enriched),
                "model": self.model,
            }

            return enriched, stats

        except Exception as e:
            # Fallback to original candidates on error
            print(f"LLM enrichment failed: {e}")
            stats = {
                "llm_called": False,
                "error": str(e),
                "total_input": len(candidates),
                "total_output": len(candidates),
            }
            return candidates, stats

    def _build_prompt(
        self,
        candidates: list[dict[str, Any]],
        market_context: dict[str, Any] | None,
    ) -> str:
        """Build prompt for LLM enrichment."""
        # Format candidates
        candidate_list = "\n".join(
            [
                f"{i + 1}. Ticker: {c['symbol']}, Reason: {c['reason']}"
                for i, c in enumerate(candidates)
            ]
        )

        # Market context (if available)
        context_str = ""
        if market_context:
            regime = market_context.get("regime", "unknown")
            spy_price = market_context.get("spy_price", 0)
            context_str = f"\n\nMarket Context:\n- Regime: {regime}\n- SPY: ${spy_price:.2f}"

        prompt = f"""You are a stock market analyst. Review these ticker candidates from RSS news and classify them.

Candidates:
{candidate_list}
{context_str}

For each ticker, determine:
1. Action: BUY (strong bullish), SELL (strong bearish), WATCH (interesting but uncertain), or IGNORE (false positive, not a real stock, or irrelevant)
2. Confidence: 0.0-1.0 (how confident are you this is a legitimate trading opportunity?)
3. Sector: Classification (e.g., "automation", "energy", "tech", "finance", "unknown")
4. Rationale: Brief explanation (max 200 chars)

Guidelines:
- IGNORE non-stock tickers (e.g., CEO, AI, acronyms that aren't stocks)
- IGNORE tickers with low relevance or insufficient information
- Use WATCH for legitimate stocks with unclear signals
- Use BUY/SELL only for clear directional opportunities
- Be conservative: when unsure, use WATCH or IGNORE

Respond with ONLY valid JSON matching this schema:
{{
  "candidates": [
    {{
      "ticker": "AAPL",
      "action": "BUY",
      "confidence": 0.85,
      "sector": "tech",
      "rationale": "Strong earnings momentum"
    }}
  ]
}}"""

        return prompt

    def _parse_response(
        self,
        response: dict[str, Any],
        original_candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Parse LLM response and filter candidates."""
        enriched = []

        llm_candidates = response.get("candidates", [])

        # Create lookup for original candidates
        original_by_ticker = {c["symbol"].upper(): c for c in original_candidates}

        for llm_cand in llm_candidates:
            ticker = llm_cand.get("ticker", "").upper()
            action = llm_cand.get("action", "WATCH").upper()
            confidence = llm_cand.get("confidence", 0.0)

            # Skip IGNORE action
            if action == "IGNORE":
                continue

            # Skip below min confidence
            if confidence < self.min_confidence:
                continue

            # Find original candidate
            original = original_by_ticker.get(ticker)
            if not original:
                continue

            # Merge LLM data into original candidate
            enriched_cand = original.copy()
            enriched_cand["action"] = action.lower()  # buy/sell/watch
            enriched_cand["confidence"] = confidence
            enriched_cand["sector"] = llm_cand.get("sector", original.get("sector"))
            enriched_cand["reason"] = llm_cand.get("rationale", original["reason"])[:200]

            enriched.append(enriched_cand)

        return enriched


def create_enricher(config: dict[str, Any]) -> CandidateEnricher | None:
    """
    Factory function to create enricher from config.

    Args:
        config: Config dict with enrichment settings

    Returns:
        CandidateEnricher if enabled, else None
    """
    if not config.get("candidates_enrichment_enabled", False):
        return None

    provider = config.get("candidates_llm_provider", "openai")
    model = config.get("candidates_llm_model", "gpt-4o-mini")
    min_confidence = config.get("candidates_min_confidence", 0.70)
    timeout = config.get("candidates_llm_timeout", 30)

    try:
        return CandidateEnricher(
            provider_type=provider,
            model=model,
            min_confidence=min_confidence,
            timeout=timeout,
        )
    except Exception as e:
        print(f"Failed to create LLM enricher: {e}")
        return None
