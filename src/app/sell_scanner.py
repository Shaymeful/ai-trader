"""AI-driven sell-side scanner for active position monitoring.

This module implements active sell-side scanning using LLM reasoning to identify
opportunities to exit positions early, before technical stop-losses trigger.

Key Features:
- News sentiment analysis for negative catalysts
- Thesis invalidation detection
- Opportunity cost evaluation (better trades available)
- Sector rotation and macro regime changes
- Relative performance analysis

Runs:
- At market open
- Every 60 minutes during market hours
- Before any new BUY orders
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.app.config import Config


@dataclass
class SellSignal:
    """Represents a sell recommendation from the scanner."""

    symbol: str
    confidence: float  # 0.0 to 1.0
    action: str  # "SELL_ALL", "SELL_HALF", "TIGHTEN_STOP", "HOLD"
    primary_reason: str  # Short description
    detailed_reasoning: list[str]  # 3-5 bullet points
    supporting_evidence: list[str]  # News headlines, data points
    invalidation_criteria: str  # What would reverse this signal
    expected_value: float | None  # Estimated EV if available
    risk_regime: str  # "bull_low_vol", "bear_high_vol", etc.
    timestamp: str  # ISO format


@dataclass
class SellScanResult:
    """Result of a complete sell scan across all positions."""

    scan_id: str
    timestamp: str
    positions_scanned: int
    sell_signals: list[SellSignal]
    market_regime: str
    scan_duration_seconds: float


class SellScanner:
    """
    AI-driven sell-side scanner using LLM reasoning.

    Actively monitors current positions and generates sell signals when:
    1. Negative catalysts detected
    2. Original thesis weakened or invalidated
    3. Better opportunities exist (opportunity cost)
    4. Risk regime changed against the position
    5. Relative underperformance vs sector/index
    """

    def __init__(self, config: Config, llm_provider=None, market_data_provider=None):
        """
        Initialize sell scanner.

        Args:
            config: Trading configuration
            llm_provider: LLM provider for reasoning (OpenAI/Anthropic)
            market_data_provider: Provider for price and indicator data
        """
        self.config = config
        self.llm_provider = llm_provider
        self.market_data_provider = market_data_provider
        self.logger = logging.getLogger("ai-trader.sell_scanner")

        # Load LLM configuration
        self.llm_model = (
            config.llm_openai_model if hasattr(config, "llm_openai_model") else "gpt-4o-mini"
        )
        self.llm_timeout = config.llm_timeout if hasattr(config, "llm_timeout") else 30

    def scan_positions(
        self,
        current_positions: dict[str, tuple[int, float]],
        market_data: dict,
        news_events: list[dict] | None = None,
    ) -> SellScanResult:
        """
        Scan all current positions for sell opportunities.

        Args:
            current_positions: Dict of symbol -> (quantity, avg_entry_price)
            market_data: Dict of symbol -> price/indicator data
            news_events: Optional list of recent news events

        Returns:
            SellScanResult with all signals generated
        """
        from datetime import UTC, datetime
        import uuid

        start_time = datetime.now(UTC)
        scan_id = str(uuid.uuid4())[:8]

        self.logger.info(
            f"[SELL SCAN {scan_id}] Starting scan of {len(current_positions)} positions"
        )

        # Determine current market regime
        market_regime = self._detect_market_regime(market_data)
        self.logger.info(f"[SELL SCAN {scan_id}] Market regime: {market_regime}")

        # Scan each position
        sell_signals = []
        for symbol, (quantity, avg_price) in current_positions.items():
            if quantity == 0:
                continue  # Skip flat positions

            self.logger.info(
                f"[SELL SCAN {scan_id}] Analyzing {symbol}: {quantity} shares @ ${avg_price:.2f}"
            )

            # Generate sell signal for this position
            signal = self._analyze_position(
                symbol=symbol,
                quantity=quantity,
                avg_entry_price=avg_price,
                market_data=market_data,
                news_events=news_events,
                market_regime=market_regime,
            )

            if signal and signal.confidence >= 0.60:  # Only include actionable signals
                sell_signals.append(signal)
                self.logger.info(
                    f"[SELL SCAN {scan_id}] SIGNAL: {symbol} - {signal.action} "
                    f"(confidence: {signal.confidence:.2f}) - {signal.primary_reason}"
                )

        end_time = datetime.now(UTC)
        duration = (end_time - start_time).total_seconds()

        result = SellScanResult(
            scan_id=scan_id,
            timestamp=start_time.isoformat(),
            positions_scanned=len([q for q, p in current_positions.values() if q != 0]),
            sell_signals=sell_signals,
            market_regime=market_regime,
            scan_duration_seconds=duration,
        )

        self.logger.info(
            f"[SELL SCAN {scan_id}] Completed in {duration:.1f}s - "
            f"Generated {len(sell_signals)} sell signals"
        )

        return result

    def _analyze_position(
        self,
        symbol: str,
        quantity: int,
        avg_entry_price: float,
        market_data: dict,
        news_events: list[dict] | None,
        market_regime: str,
    ) -> SellSignal | None:
        """
        Analyze a single position and generate sell signal if appropriate.

        Uses LLM reasoning to evaluate:
        1. Recent news sentiment
        2. Price action vs entry price
        3. Relative performance vs sector/index
        4. Risk regime alignment
        5. Opportunity cost

        Args:
            symbol: Stock symbol
            quantity: Current position size
            avg_entry_price: Average entry price
            market_data: Market data dict
            news_events: Recent news events
            market_regime: Current market regime

        Returns:
            SellSignal if sell recommended, None if hold
        """
        # Get current price and performance
        current_price = market_data.get(symbol, {}).get("price", avg_entry_price)
        pnl_pct = ((current_price - avg_entry_price) / avg_entry_price) * 100

        # Filter news for this symbol
        relevant_news = self._filter_news_for_symbol(symbol, news_events) if news_events else []

        # Build analysis prompt for LLM
        prompt = self._build_sell_analysis_prompt(
            symbol=symbol,
            quantity=quantity,
            avg_entry_price=avg_entry_price,
            current_price=current_price,
            pnl_pct=pnl_pct,
            market_data=market_data.get(symbol, {}),
            news_events=relevant_news,
            market_regime=market_regime,
        )

        # Get LLM reasoning (if available)
        if self.llm_provider:
            llm_response = self._get_llm_sell_reasoning(prompt)
        else:
            # Fallback to heuristic-based analysis
            llm_response = self._heuristic_sell_analysis(
                symbol, pnl_pct, market_data.get(symbol, {}), market_regime
            )

        # Parse response into SellSignal
        return self._parse_sell_response(symbol, llm_response, pnl_pct, market_regime)

    def _build_sell_analysis_prompt(
        self,
        symbol: str,
        quantity: int,
        avg_entry_price: float,
        current_price: float,
        pnl_pct: float,
        market_data: dict,
        news_events: list[dict],
        market_regime: str,
    ) -> str:
        """Build prompt for LLM sell analysis."""
        # Format news headlines
        news_summary = (
            "\n".join(
                [
                    f"- {event.get('headline', 'N/A')}"
                    for event in news_events[:5]  # Top 5 most recent
                ]
            )
            if news_events
            else "No recent news available"
        )

        # Format market data
        ma = market_data.get("ma", current_price)
        zscore = market_data.get("zscore", 0.0)

        prompt = f"""Analyze whether to SELL this position:

POSITION:
- Symbol: {symbol}
- Quantity: {quantity} shares
- Entry Price: ${avg_entry_price:.2f}
- Current Price: ${current_price:.2f}
- PnL: {pnl_pct:+.2f}%

MARKET DATA:
- Price vs MA: {current_price:.2f} vs {ma:.2f} ({((current_price - ma) / ma * 100):+.1f}%)
- Z-Score: {zscore:.2f}
- Market Regime: {market_regime}

RECENT NEWS (Last 24-72 hours):
{news_summary}

EVALUATION CRITERIA:
1. Has the original thesis weakened or been invalidated?
2. Are there negative catalysts or deteriorating fundamentals?
3. Is capital better deployed elsewhere (opportunity cost)?
4. Is the stock underperforming its sector/index significantly?
5. Has the risk regime changed against this position?

RESPOND WITH JSON:
{{
  "action": "SELL_ALL" | "SELL_HALF" | "TIGHTEN_STOP" | "HOLD",
  "confidence": 0.0-1.0,
  "primary_reason": "One-sentence summary",
  "detailed_reasoning": ["Bullet 1", "Bullet 2", "Bullet 3"],
  "supporting_evidence": ["Evidence 1", "Evidence 2"],
  "invalidation_criteria": "What would reverse this signal",
  "expected_value": null or number (estimated EV)
}}

Be conservative: Only recommend SELL if confidence >= 0.70 for SELL_ALL, >= 0.60 for SELL_HALF.
"""
        return prompt

    def _get_llm_sell_reasoning(self, prompt: str) -> dict:
        """Get LLM reasoning for sell decision."""
        try:
            if not self.llm_provider:
                return self._fallback_response()

            # Call LLM provider
            response = self.llm_provider.generate_structured_json(
                prompt=prompt,
                schema={
                    "action": "string",
                    "confidence": "number",
                    "primary_reason": "string",
                    "detailed_reasoning": ["string"],
                    "supporting_evidence": ["string"],
                    "invalidation_criteria": "string",
                    "expected_value": "number or null",
                },
                temperature=0.3,  # Lower temperature for more consistent reasoning
                max_tokens=800,
            )

            return response

        except Exception as e:
            self.logger.error(f"LLM sell reasoning failed: {e}")
            return self._fallback_response()

    def _heuristic_sell_analysis(
        self, symbol: str, pnl_pct: float, market_data: dict, market_regime: str
    ) -> dict:
        """Fallback heuristic-based sell analysis when LLM unavailable."""
        # Simple heuristics
        action = "HOLD"
        confidence = 0.5
        reasons = []

        # Check for stop-loss trigger
        if pnl_pct < -5.0:
            action = "SELL_ALL"
            confidence = 0.80
            reasons.append(f"Stop-loss triggered: PnL {pnl_pct:.1f}% < -5%")

        # Check for take-profit
        elif pnl_pct > 10.0:
            action = "SELL_HALF"
            confidence = 0.70
            reasons.append(f"Take-profit: PnL {pnl_pct:.1f}% > 10%, trim position")

        # Check price vs MA (trend breakdown)
        price = market_data.get("price", 0)
        ma = market_data.get("ma", price)
        if price < ma * 0.98:  # Price 2% below MA
            action = "SELL_HALF"
            confidence = 0.65
            reasons.append(f"Trend breakdown: Price {((price - ma) / ma * 100):.1f}% below MA")

        if not reasons:
            reasons.append("No clear sell signal - holding position")

        return {
            "action": action,
            "confidence": confidence,
            "primary_reason": reasons[0] if reasons else "No clear signal",
            "detailed_reasoning": reasons,
            "supporting_evidence": ["Heuristic-based analysis"],
            "invalidation_criteria": "Price recovery above MA or positive news catalyst",
            "expected_value": None,
        }

    def _parse_sell_response(
        self, symbol: str, response: dict, pnl_pct: float, market_regime: str
    ) -> SellSignal | None:
        """Parse LLM response into SellSignal."""
        action = response.get("action", "HOLD")
        confidence = response.get("confidence", 0.5)

        # Only create signal if actionable
        if action == "HOLD" and confidence < 0.60:
            return None

        return SellSignal(
            symbol=symbol,
            confidence=confidence,
            action=action,
            primary_reason=response.get("primary_reason", "No reason provided"),
            detailed_reasoning=response.get("detailed_reasoning", []),
            supporting_evidence=response.get("supporting_evidence", []),
            invalidation_criteria=response.get("invalidation_criteria", "Unknown"),
            expected_value=response.get("expected_value"),
            risk_regime=market_regime,
            timestamp=datetime.now(UTC).isoformat(),
        )

    def _filter_news_for_symbol(self, symbol: str, news_events: list[dict]) -> list[dict]:
        """Filter news events relevant to a specific symbol."""
        if not news_events:
            return []

        return [
            event
            for event in news_events
            if event.get("symbol") == symbol or symbol in (event.get("headline") or "").upper()
        ][:10]  # Max 10 most recent

    def _detect_market_regime(self, market_data: dict) -> str:
        """
        Detect current market regime.

        Simple implementation based on SPY if available.
        Returns: "bull_low_vol", "bull_high_vol", "bear_low_vol", "bear_high_vol", "unknown"
        """
        spy_data = market_data.get("SPY", {})
        price = spy_data.get("price")
        ma = spy_data.get("ma")

        if price is None or ma is None:
            return "unknown"

        # Determine trend
        if price > ma:
            trend = "bull"
        else:
            trend = "bear"

        # Simplified volatility (would need historical data for real calculation)
        # For now, use z-score as proxy
        zscore = abs(spy_data.get("zscore", 0.0))
        if zscore > 1.5:
            vol = "high_vol"
        else:
            vol = "low_vol"

        return f"{trend}_{vol}"

    def _fallback_response(self) -> dict:
        """Fallback response when LLM fails."""
        return {
            "action": "HOLD",
            "confidence": 0.50,
            "primary_reason": "LLM unavailable - defaulting to hold",
            "detailed_reasoning": ["Cannot perform full analysis without LLM"],
            "supporting_evidence": [],
            "invalidation_criteria": "Manual review required",
            "expected_value": None,
        }

    def save_scan_result(self, result: SellScanResult, output_dir: Path = Path("out/sell_scans")):
        """Save scan result to disk for analysis."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save as JSON
        output_file = output_dir / f"sell_scan_{result.scan_id}_{result.timestamp[:10]}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(asdict(result), f, indent=2)

        self.logger.info(f"[SELL SCAN {result.scan_id}] Saved results to {output_file}")

        # Append to history log
        history_file = output_dir / "sell_scan_history.jsonl"
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(result)) + "\n")
