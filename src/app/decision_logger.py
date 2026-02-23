"""Decision logging for explainability and analysis.

Logs every BUY/SELL decision with:
- Action (BUY, SELL, HOLD, TRIM)
- Confidence score
- Expected value estimate
- Risk regime classification
- Primary reasoning
- Invalidation criteria

Format: Structured JSON (one line per decision) for easy analysis
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class TradingDecision:
    """Represents a single trading decision with full context."""

    decision_id: str
    timestamp: str  # ISO format UTC
    symbol: str
    action: str  # "BUY", "SELL", "SELL_HALF", "HOLD", "TRIM"
    quantity: int | float
    price: float
    confidence: float  # 0.0 to 1.0
    expected_value: float | None  # Estimated EV if available
    risk_regime: str  # "bull_low_vol", "bear_high_vol", etc.
    strategy: str | None  # Strategy that generated the signal
    primary_reason: str  # One-sentence summary
    detailed_reasoning: list[str]  # 3-5 bullet points
    supporting_data: dict  # Market data, indicators, etc.
    invalidation_criteria: str  # What would reverse this decision
    position_context: dict | None  # Current position details if applicable
    execution_result: str | None  # "EXECUTED", "SKIPPED", "FAILED"


@dataclass
class DecisionBatch:
    """Batch of decisions from one trading loop iteration."""

    batch_id: str
    timestamp: str
    iteration_number: int
    market_regime: str
    total_decisions: int
    buy_count: int
    sell_count: int
    hold_count: int
    decisions: list[TradingDecision]


class DecisionLogger:
    """
    Structured decision logger for trade explainability.

    Logs all trading decisions with full context for:
    - Post-trade analysis
    - Strategy debugging
    - Regulatory compliance
    - Performance attribution
    """

    def __init__(self, output_dir: Path = Path("out/decisions")):
        """
        Initialize decision logger.

        Args:
            output_dir: Directory for decision logs
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("ai-trader.decisions")

        # Separate log files for different actions
        self.buy_log = self.output_dir / "decisions_buy.jsonl"
        self.sell_log = self.output_dir / "decisions_sell.jsonl"
        self.all_log = self.output_dir / "decisions_all.jsonl"
        self.daily_log = self.output_dir / f"decisions_{datetime.now(UTC).strftime('%Y%m%d')}.jsonl"

    def log_decision(self, decision: TradingDecision):
        """
        Log a single trading decision.

        Args:
            decision: TradingDecision object
        """
        decision_json = json.dumps(asdict(decision))

        # Log to all decisions file
        with open(self.all_log, "a", encoding="utf-8") as f:
            f.write(decision_json + "\n")

        # Log to action-specific file
        if decision.action in ["BUY"]:
            with open(self.buy_log, "a", encoding="utf-8") as f:
                f.write(decision_json + "\n")
        elif decision.action in ["SELL", "SELL_HALF", "SELL_ALL", "TRIM"]:
            with open(self.sell_log, "a", encoding="utf-8") as f:
                f.write(decision_json + "\n")

        # Log to daily file
        with open(self.daily_log, "a", encoding="utf-8") as f:
            f.write(decision_json + "\n")

        # Also log human-readable summary to console
        self._log_human_readable(decision)

    def log_batch(self, batch: DecisionBatch):
        """
        Log a batch of decisions from one iteration.

        Args:
            batch: DecisionBatch object
        """
        batch_file = self.output_dir / f"batch_{batch.batch_id}.json"
        with open(batch_file, "w", encoding="utf-8") as f:
            json.dump(asdict(batch), f, indent=2)

        # Log each individual decision
        for decision in batch.decisions:
            self.log_decision(decision)

        self.logger.info(
            f"[DECISION BATCH {batch.batch_id}] Logged {batch.total_decisions} decisions: "
            f"{batch.buy_count} BUY, {batch.sell_count} SELL, {batch.hold_count} HOLD"
        )

    def _log_human_readable(self, decision: TradingDecision):
        """Log human-readable summary to console."""
        # Format action with color indicators (ASCII-safe for Windows console)
        action_emoji = {
            "BUY": "[BUY]",
            "SELL": "[SELL]",
            "SELL_HALF": "[SELL_HALF]",
            "SELL_ALL": "[SELL_ALL]",
            "HOLD": "[HOLD]",
            "TRIM": "[TRIM]",
        }

        action_display = action_emoji.get(decision.action, decision.action)

        # Build summary
        summary_lines = [
            "",
            "=" * 80,
            f"{action_display} DECISION: {decision.symbol}",
            "=" * 80,
            f"Timestamp:   {decision.timestamp}",
            f"Decision ID: {decision.decision_id}",
            f"",
            f"ACTION:      {decision.action} {decision.quantity} shares @ ${decision.price:.2f}",
            f"Confidence:  {decision.confidence:.2f} ({self._confidence_label(decision.confidence)})",
            f"Risk Regime: {decision.risk_regime}",
        ]

        if decision.expected_value is not None:
            summary_lines.append(f"Expected Value: ${decision.expected_value:.2f}")

        if decision.strategy:
            summary_lines.append(f"Strategy:    {decision.strategy}")

        summary_lines.extend([
            f"",
            f"PRIMARY REASON:",
            f"  {decision.primary_reason}",
            f"",
            f"DETAILED REASONING:",
        ])

        for i, reason in enumerate(decision.detailed_reasoning, 1):
            summary_lines.append(f"  {i}. {reason}")

        if decision.supporting_data:
            summary_lines.extend([
                f"",
                f"SUPPORTING DATA:",
            ])
            for key, value in list(decision.supporting_data.items())[:5]:  # Show top 5
                if isinstance(value, (int, float)):
                    summary_lines.append(f"  {key}: {value:.2f}")
                else:
                    summary_lines.append(f"  {key}: {value}")

        summary_lines.extend([
            f"",
            f"INVALIDATION CRITERIA:",
            f"  {decision.invalidation_criteria}",
        ])

        if decision.execution_result:
            summary_lines.append(f"")
            summary_lines.append(f"EXECUTION: {decision.execution_result}")

        summary_lines.append("=" * 80)

        # Log to console
        summary = "\n".join(summary_lines)
        self.logger.info(summary)

        # Also print to stdout for visibility (with error handling for Windows encoding issues)
        try:
            print(summary)
        except (OSError, UnicodeEncodeError) as e:
            # Fallback: print with errors replaced if stdout can't handle the characters
            try:
                print(summary.encode('utf-8', errors='replace').decode('utf-8', errors='replace'))
            except Exception:
                # If that fails too, just log it
                self.logger.warning(f"Could not print decision summary to stdout: {e}")

    def _confidence_label(self, confidence: float) -> str:
        """Convert confidence score to human-readable label."""
        if confidence >= 0.90:
            return "VERY HIGH"
        elif confidence >= 0.75:
            return "HIGH"
        elif confidence >= 0.60:
            return "MEDIUM"
        elif confidence >= 0.50:
            return "LOW"
        else:
            return "VERY LOW"

    def generate_summary_report(self, start_date: str | None = None, end_date: str | None = None) -> dict:
        """
        Generate summary report of all decisions in a date range.

        Args:
            start_date: Start date (ISO format), defaults to today
            end_date: End date (ISO format), defaults to today

        Returns:
            Dict with summary statistics
        """
        if not start_date:
            start_date = datetime.now(UTC).strftime("%Y-%m-%d")
        if not end_date:
            end_date = start_date

        # Load decisions from files
        decisions = self._load_decisions_in_range(start_date, end_date)

        if not decisions:
            return {
                "date_range": f"{start_date} to {end_date}",
                "total_decisions": 0,
                "message": "No decisions found in this range",
            }

        # Calculate statistics
        buy_decisions = [d for d in decisions if d["action"] == "BUY"]
        sell_decisions = [d for d in decisions if d["action"] in ["SELL", "SELL_HALF", "SELL_ALL", "TRIM"]]
        hold_decisions = [d for d in decisions if d["action"] == "HOLD"]

        avg_confidence = sum(d["confidence"] for d in decisions) / len(decisions)
        avg_buy_confidence = (
            sum(d["confidence"] for d in buy_decisions) / len(buy_decisions)
            if buy_decisions
            else 0
        )
        avg_sell_confidence = (
            sum(d["confidence"] for d in sell_decisions) / len(sell_decisions)
            if sell_decisions
            else 0
        )

        return {
            "date_range": f"{start_date} to {end_date}",
            "total_decisions": len(decisions),
            "buy_count": len(buy_decisions),
            "sell_count": len(sell_decisions),
            "hold_count": len(hold_decisions),
            "avg_confidence": round(avg_confidence, 3),
            "avg_buy_confidence": round(avg_buy_confidence, 3) if buy_decisions else None,
            "avg_sell_confidence": round(avg_sell_confidence, 3) if sell_decisions else None,
            "symbols_traded": list(set(d["symbol"] for d in decisions)),
            "unique_symbols": len(set(d["symbol"] for d in decisions)),
        }

    def _load_decisions_in_range(self, start_date: str, end_date: str) -> list[dict]:
        """Load all decisions in a date range from log files."""
        decisions = []

        # Load from all_log file
        if self.all_log.exists():
            with open(self.all_log, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        decision = json.loads(line.strip())
                        decision_date = decision["timestamp"][:10]  # Extract YYYY-MM-DD
                        if start_date <= decision_date <= end_date:
                            decisions.append(decision)
                    except (json.JSONDecodeError, KeyError):
                        continue

        return decisions

    def export_to_csv(self, output_file: Path, start_date: str | None = None, end_date: str | None = None):
        """
        Export decisions to CSV for analysis in Excel/Python.

        Args:
            output_file: Output CSV file path
            start_date: Start date filter
            end_date: End date filter
        """
        import csv

        decisions = self._load_decisions_in_range(
            start_date or "2000-01-01",
            end_date or "2099-12-31"
        )

        if not decisions:
            self.logger.warning("No decisions to export")
            return

        # Write CSV
        fieldnames = [
            "timestamp", "symbol", "action", "quantity", "price",
            "confidence", "risk_regime", "strategy", "primary_reason",
            "execution_result"
        ]

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for decision in decisions:
                writer.writerow({
                    "timestamp": decision["timestamp"],
                    "symbol": decision["symbol"],
                    "action": decision["action"],
                    "quantity": decision["quantity"],
                    "price": decision["price"],
                    "confidence": decision["confidence"],
                    "risk_regime": decision["risk_regime"],
                    "strategy": decision.get("strategy", "N/A"),
                    "primary_reason": decision["primary_reason"],
                    "execution_result": decision.get("execution_result", "N/A"),
                })

        self.logger.info(f"Exported {len(decisions)} decisions to {output_file}")


def create_decision_from_intent(
    intent,
    price: float,
    risk_regime: str,
    execution_result: str | None = None,
) -> TradingDecision:
    """
    Create a TradingDecision from a PositionIntent.

    Helper function for easy integration with existing code.

    Args:
        intent: PositionIntent object
        price: Current price
        risk_regime: Current market regime
        execution_result: Optional execution result

    Returns:
        TradingDecision object
    """
    import uuid

    # Determine action based on target_quantity
    if intent.target_quantity > 0:
        action = "BUY"
    elif intent.target_quantity < 0:
        action = "SELL"
    else:
        action = "HOLD"

    return TradingDecision(
        decision_id=str(uuid.uuid4())[:8],
        timestamp=datetime.now(UTC).isoformat(),
        symbol=intent.symbol,
        action=action,
        quantity=abs(intent.target_quantity),
        price=price,
        confidence=intent.conviction,
        expected_value=None,  # Could be calculated if we have more data
        risk_regime=risk_regime,
        strategy=None,  # Would need to pass this in
        primary_reason=intent.reason,
        detailed_reasoning=[intent.reason],  # Could expand this
        supporting_data={},  # Could add market data here
        invalidation_criteria="Technical signal reversal or stop-loss trigger",
        position_context=None,
        execution_result=execution_result,
    )
