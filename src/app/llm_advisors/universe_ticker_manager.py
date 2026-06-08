"""
Universe Ticker Manager - Dynamic ticker add/remove recommendations.

This AI Co-Pilot feature analyzes:
- Current positions
- Current universe tickers
- Current candidates from selector
- Market conditions

And proposes:
- add_candidates: New tickers to add to universe (tech/battery/energy focus)
- remove_candidates: Underperforming tickers to remove
- buy_bias: Existing tickers to prioritize for buying
- sell_bias: Existing tickers to consider selling

SAFETY:
- Advisory only (does not execute changes automatically)
- Respects existing approval workflows
- Budget-limited (max_output_tokens)
- Never blocks loop
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.app.config import Config

logger = logging.getLogger("ai-trader.copilot.ticker_manager")


@dataclass
class TickerAction:
    """Represents a single ticker action recommendation."""

    ticker: str
    action: str  # "add", "remove", "buy_bias", "sell_bias"
    confidence: float  # 0.0 to 1.0
    reason: str  # Short explanation
    sector: str | None = None  # Optional sector classification


@dataclass
class TickerManagerRecommendation:
    """Complete set of ticker management recommendations."""

    timestamp: str
    add_candidates: list[TickerAction]
    remove_candidates: list[TickerAction]
    buy_bias: list[TickerAction]
    sell_bias: list[TickerAction]
    market_context: str  # Brief market regime description
    focus_areas: list[str]  # e.g., ["tech", "battery", "energy"]


class UniverseTickerManager:
    """
    AI-powered universe ticker manager.

    Analyzes positions, universe, and candidates to recommend dynamic ticker changes
    with a focus on tech/battery/energy opportunities.
    """

    def __init__(self, config: Config, llm_provider=None):
        """
        Initialize universe ticker manager.

        Args:
            config: Trading configuration
            llm_provider: LLM provider for reasoning (OpenAI/Anthropic)
        """
        self.config = config
        self.llm_provider = llm_provider
        self.output_dir = Path("logs/ticker_manager")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_recommendations(
        self,
        current_positions: list[dict[str, Any]],
        universe_symbols: list[str],
        candidates: list[dict[str, Any]],
        market_data: dict[str, Any] | None = None,
    ) -> TickerManagerRecommendation | None:
        """
        Generate ticker management recommendations.

        Args:
            current_positions: List of current position dicts
            universe_symbols: List of symbols in current universe
            candidates: List of candidate dicts from selector
            market_data: Optional market data context

        Returns:
            TickerManagerRecommendation or None if LLM unavailable
        """
        if not self.llm_provider:
            logger.warning("No LLM provider available for ticker manager")
            return None

        if not self.config.ai_copilot_universe_ticker_manager_enabled:
            logger.debug("Universe ticker manager disabled in config")
            return None

        try:
            # Build prompt
            prompt = self._build_prompt(
                current_positions, universe_symbols, candidates, market_data
            )

            # Call LLM
            max_tokens = self.config.ai_copilot_universe_ticker_manager_max_tokens
            response = self.llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.3,  # Lower temperature for more focused recommendations
            )

            # Parse response
            recommendation = self._parse_response(response)

            # Save recommendation
            self._save_recommendation(recommendation)

            return recommendation

        except Exception as e:
            logger.error(f"Failed to generate ticker recommendations: {e}")
            return None

    def _build_prompt(
        self,
        current_positions: list[dict[str, Any]],
        universe_symbols: list[str],
        candidates: list[dict[str, Any]],
        market_data: dict[str, Any] | None,
    ) -> str:
        """Build LLM prompt for ticker management."""
        # Extract position symbols
        position_symbols = [p.get("symbol") for p in current_positions if "symbol" in p]

        # Extract candidate symbols with confidence
        candidate_info = []
        for c in candidates[:20]:  # Limit to top 20
            symbol = c.get("symbol", "")
            confidence = c.get("confidence", 0.0)
            action = c.get("action", "")
            candidate_info.append(f"{symbol} ({action}, conf={confidence:.2f})")

        prompt = f"""You are an AI trading advisor focused on tech, battery, and energy sectors.

**CURRENT STATE:**
- Universe: {len(universe_symbols)} symbols - {", ".join(universe_symbols[:15])}{"..." if len(universe_symbols) > 15 else ""}
- Positions: {len(position_symbols)} symbols - {", ".join(position_symbols) if position_symbols else "None"}
- Top Candidates: {", ".join(candidate_info[:10]) if candidate_info else "None"}

**TASK:**
Recommend ticker changes with focus on tech/battery/energy opportunities.

**OUTPUT FORMAT (JSON):**
```json
{{
  "market_context": "brief market regime description",
  "focus_areas": ["tech", "battery", "energy"],
  "add_candidates": [
    {{"ticker": "SYM", "confidence": 0.75, "reason": "why add", "sector": "tech"}},
  ],
  "remove_candidates": [
    {{"ticker": "SYM", "confidence": 0.80, "reason": "why remove", "sector": null}},
  ],
  "buy_bias": [
    {{"ticker": "SYM", "confidence": 0.70, "reason": "why prioritize", "sector": "energy"}},
  ],
  "sell_bias": [
    {{"ticker": "SYM", "confidence": 0.65, "reason": "why consider selling", "sector": null}},
  ]
}}
```

**RULES:**
1. add_candidates: Only tech/battery/energy tickers not in universe
2. remove_candidates: Only low-performing/off-theme tickers (max 1-2)
3. buy_bias: Existing universe tickers with strong catalysts (max 3-5)
4. sell_bias: Current positions with weakening thesis (max 2-3)
5. Confidence: 0.50-0.65 = weak, 0.65-0.80 = moderate, 0.80+ = strong
6. Focus: Tech (AI, chips, software), Battery (EVs, storage), Energy (renewables, XLE)

Provide only the JSON output, no additional text."""

        return prompt

    def _parse_response(self, response: str) -> TickerManagerRecommendation:
        """Parse LLM response into TickerManagerRecommendation."""
        try:
            # Extract JSON from response (handle markdown code blocks)
            response = response.strip()
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                response = response[start:end].strip()

            data = json.loads(response)

            # Parse actions
            def parse_actions(actions_list: list[dict]) -> list[TickerAction]:
                return [
                    TickerAction(
                        ticker=a.get("ticker", "").upper(),
                        action="",  # Set by caller
                        confidence=float(a.get("confidence", 0.5)),
                        reason=a.get("reason", ""),
                        sector=a.get("sector"),
                    )
                    for a in actions_list
                ]

            add_actions = parse_actions(data.get("add_candidates", []))
            for a in add_actions:
                a.action = "add"

            remove_actions = parse_actions(data.get("remove_candidates", []))
            for a in remove_actions:
                a.action = "remove"

            buy_bias_actions = parse_actions(data.get("buy_bias", []))
            for a in buy_bias_actions:
                a.action = "buy_bias"

            sell_bias_actions = parse_actions(data.get("sell_bias", []))
            for a in sell_bias_actions:
                a.action = "sell_bias"

            return TickerManagerRecommendation(
                timestamp=datetime.utcnow().isoformat(),
                add_candidates=add_actions,
                remove_candidates=remove_actions,
                buy_bias=buy_bias_actions,
                sell_bias=sell_bias_actions,
                market_context=data.get("market_context", "unknown"),
                focus_areas=data.get("focus_areas", ["tech", "battery", "energy"]),
            )

        except Exception as e:
            logger.error(f"Failed to parse ticker manager response: {e}")
            # Return empty recommendation
            return TickerManagerRecommendation(
                timestamp=datetime.utcnow().isoformat(),
                add_candidates=[],
                remove_candidates=[],
                buy_bias=[],
                sell_bias=[],
                market_context="parse_error",
                focus_areas=[],
            )

    def _save_recommendation(self, recommendation: TickerManagerRecommendation):
        """Save recommendation to JSONL file for history."""
        try:
            output_file = self.output_dir / "recommendations.jsonl"
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(recommendation)) + "\n")
        except Exception as e:
            logger.warning(f"Failed to save ticker recommendation: {e}")

    def get_latest_recommendation(self) -> TickerManagerRecommendation | None:
        """Get the most recent recommendation from history."""
        try:
            output_file = self.output_dir / "recommendations.jsonl"
            if not output_file.exists():
                return None

            with open(output_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if not lines:
                return None

            # Parse last line
            data = json.loads(lines[-1])
            return TickerManagerRecommendation(
                timestamp=data["timestamp"],
                add_candidates=[TickerAction(**a) for a in data["add_candidates"]],
                remove_candidates=[TickerAction(**a) for a in data["remove_candidates"]],
                buy_bias=[TickerAction(**a) for a in data["buy_bias"]],
                sell_bias=[TickerAction(**a) for a in data["sell_bias"]],
                market_context=data["market_context"],
                focus_areas=data["focus_areas"],
            )

        except Exception as e:
            logger.warning(f"Failed to load latest recommendation: {e}")
            return None
