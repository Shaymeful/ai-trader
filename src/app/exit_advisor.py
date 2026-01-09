"""Exit Advisor module for AI-driven position exit recommendations.

This module wraps the sell_scanner to:
1. Scan open positions for exit opportunities
2. Emit SELL candidates into the existing candidate pipeline
3. Apply per-symbol cooldowns to avoid repeated spam
4. Log telemetry to out/exit_advisor/events.jsonl

This makes "what should I sell?" a first-class AI concern.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .advisor_telemetry import create_telemetry_context
from .sell_scanner import SellScanner


@dataclass
class ExitCandidate:
    """Exit candidate emitted into the candidate pipeline."""

    candidate_id: str
    created_at: str
    expires_at: str
    symbol: str
    action: str  # "sell"
    confidence: float
    horizon: str  # "intraday" | "swing"
    sector: str | None
    event_type: str  # "exit_advisor"
    tags: list[str]
    reason: str


class ExitAdvisor:
    """
    Exit Advisor that scans positions and emits SELL candidates.

    Integrates sell_scanner with the candidate pipeline and adds:
    - Per-symbol cooldown to avoid spam
    - Telemetry logging
    - Candidate emission
    """

    def __init__(
        self,
        sell_scanner: SellScanner,
        cooldown_hours: int = 4,
        output_dir: Path = Path("out/exit_advisor"),
    ):
        """
        Initialize Exit Advisor.

        Args:
            sell_scanner: SellScanner instance
            cooldown_hours: Hours to wait before re-scanning same symbol
            output_dir: Directory for exit advisor outputs
        """
        self.sell_scanner = sell_scanner
        self.cooldown_hours = cooldown_hours
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.output_dir / "events.jsonl"
        self.logger = logging.getLogger("ai-trader.exit_advisor")

        # Cooldown tracking: symbol -> last_scan_time
        self.last_scan_times = self._load_cooldowns()

    def _load_cooldowns(self) -> dict[str, datetime]:
        """Load cooldown state from events file."""
        cooldowns = {}
        if not self.events_file.exists():
            return cooldowns

        cutoff = datetime.now(UTC) - timedelta(hours=self.cooldown_hours)

        with open(self.events_file, encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    if event.get("event_type") == "exit_signal":
                        symbol = event.get("symbol")
                        timestamp_str = event.get("timestamp")
                        if symbol and timestamp_str:
                            timestamp = datetime.fromisoformat(timestamp_str)
                            if timestamp > cutoff:
                                cooldowns[symbol] = timestamp
                except (json.JSONDecodeError, ValueError):
                    continue

        return cooldowns

    def _is_on_cooldown(self, symbol: str) -> bool:
        """Check if symbol is on cooldown."""
        last_scan = self.last_scan_times.get(symbol)
        if not last_scan:
            return False

        elapsed = datetime.now(UTC) - last_scan
        return elapsed < timedelta(hours=self.cooldown_hours)

    def _update_cooldown(self, symbol: str) -> None:
        """Update cooldown timestamp for symbol."""
        self.last_scan_times[symbol] = datetime.now(UTC)

    def scan_and_emit_candidates(
        self,
        current_positions: dict[str, tuple[int, float]],
        market_data: dict,
        news_events: list[dict] | None = None,
        market_regime: str | None = None,
    ) -> list[ExitCandidate]:
        """
        Scan positions and emit exit candidates.

        Args:
            current_positions: Dict of symbol -> (quantity, avg_entry_price)
            market_data: Market data dict
            news_events: Recent news events
            market_regime: Current market regime

        Returns:
            List of ExitCandidate objects
        """
        # Start telemetry tracking
        providers = []
        if self.sell_scanner.llm_provider:
            providers.append(self.sell_scanner.llm_provider.get_provider_name())

        model_name = self.sell_scanner.llm_model if providers else None

        context = create_telemetry_context(
            advisor_type="exit_advisor",
            providers=providers,
            model_name=model_name,
            universe_size=len(current_positions),
            news_count=len(news_events) if news_events else 0,
            regime=market_regime,
        )

        # Filter out positions on cooldown
        positions_to_scan = {}
        filtered_cooldown = 0

        for symbol, position_data in current_positions.items():
            if self._is_on_cooldown(symbol):
                filtered_cooldown += 1
                self.logger.debug(f"Skipping {symbol} - on cooldown")
                continue
            positions_to_scan[symbol] = position_data

        if filtered_cooldown > 0:
            context.add_filtered("cooldown", filtered_cooldown)

        if not positions_to_scan:
            context.add_rationale("No positions to scan (all on cooldown)")
            context.set_final_count(0)
            event = context.finalize()
            from .advisor_telemetry import AdvisorTelemetry

            telemetry = AdvisorTelemetry()
            telemetry.log_run(event)
            self.logger.info("No positions to scan - all on cooldown")
            return []

        try:
            # Run sell scanner
            scan_result = self.sell_scanner.scan_positions(
                positions_to_scan, market_data, news_events
            )

            context.add_raw_ideas(len(scan_result.sell_signals))

            # Filter signals and create candidates
            exit_candidates = []
            filtered_confidence = 0
            filtered_hold = 0

            for signal in scan_result.sell_signals:
                # Filter HOLD signals
                if signal.action == "HOLD":
                    filtered_hold += 1
                    continue

                # Filter low confidence
                if signal.confidence < 0.60:
                    filtered_confidence += 1
                    continue

                # Create candidate
                candidate = self._create_exit_candidate(signal, market_regime)
                exit_candidates.append(candidate)

                # Update cooldown
                self._update_cooldown(signal.symbol)

                # Log exit signal event
                self._log_exit_signal(signal, scan_result.scan_id)

            # Update telemetry
            if filtered_confidence > 0:
                context.add_filtered("confidence_too_low", filtered_confidence)
            if filtered_hold > 0:
                context.add_filtered("hold_signal", filtered_hold)

            context.set_final_count(len(exit_candidates))

            if exit_candidates:
                context.add_rationale(
                    f"Generated {len(exit_candidates)} exit signals from {len(positions_to_scan)} positions"
                )
            else:
                context.add_rationale("No exit signals met confidence threshold")

            # Finalize telemetry
            event = context.finalize()
            from .advisor_telemetry import AdvisorTelemetry

            telemetry = AdvisorTelemetry()
            telemetry.log_run(event)

            return exit_candidates

        except Exception as e:
            self.logger.error(f"Exit advisor scan failed: {e}")
            context.set_status("error", str(e))
            event = context.finalize()
            from .advisor_telemetry import AdvisorTelemetry

            telemetry = AdvisorTelemetry()
            telemetry.log_run(event)
            return []

    def _create_exit_candidate(self, signal, market_regime: str | None) -> ExitCandidate:
        """Create ExitCandidate from SellSignal."""
        now = datetime.now(UTC)

        # Determine TTL based on action: SELL_ALL is urgent (2h), others less urgent (4h)
        ttl_hours = 2 if signal.action == "SELL_ALL" else 4
        expires_at = now + timedelta(hours=ttl_hours)

        # Map action to candidate action
        action = "sell"  # All exit signals are sell actions

        # Determine horizon (shorter for urgent exits)
        horizon = "intraday" if signal.action == "SELL_ALL" else "swing"

        return ExitCandidate(
            candidate_id=f"exit-{now.strftime('%Y%m%d%H%M%S')}-{signal.symbol}",
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            symbol=signal.symbol,
            action=action,
            confidence=signal.confidence,
            horizon=horizon,
            sector=None,  # Could be enriched if needed
            event_type="exit_advisor",
            tags=["exit", signal.action.lower(), market_regime or "unknown"],
            reason=f"{signal.action}: {signal.primary_reason}",
        )

    def _log_exit_signal(self, signal, scan_id: str) -> None:
        """Log exit signal event to events.jsonl."""
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": "exit_signal",
            "scan_id": scan_id,
            "symbol": signal.symbol,
            "action": signal.action,
            "confidence": signal.confidence,
            "primary_reason": signal.primary_reason,
            "risk_regime": signal.risk_regime,
        }

        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
