"""
Central LLM client for AI Co-Pilot with budget gates and graceful degradation.

SAFETY PRINCIPLES:
1. Never blocks loop - all failures return None/fallback values
2. Budget gates prevent runaway costs
3. All LLM calls are logged
4. Retries with exponential backoff
5. Respects global AI_COPILOT_ENABLED and AI_COPILOT_DRY_RUN env vars
"""

import logging
import os
import time
from typing import Any

from src.app.config import Config
from src.app.llm.factory import create_provider

logger = logging.getLogger("ai-trader.copilot")


class BudgetExceededError(Exception):
    """Raised when LLM call budget is exceeded."""

    pass


class CoPilotClient:
    """Budget-gated LLM client for AI Co-Pilot advisory features.

    This client:
    - Tracks call count per run and enforces max_calls_per_run budget
    - Enforces timeout and max_tokens from config
    - Retries with exponential backoff (max 3 retries)
    - Gracefully degrades on all failures (returns None instead of raising)
    - Logs all calls and failures for debugging
    - Respects AI_COPILOT_DRY_RUN=1 (skips real calls, returns mock data)
    """

    def __init__(self, config: Config):
        """
        Initialize CoPilot client.

        Args:
            config: Application configuration with ai_copilot settings
        """
        self.config = config
        self.call_count = 0

        # Check for dry-run mode (testing/debugging)
        self.dry_run = os.getenv("AI_COPILOT_DRY_RUN") == "1"

        # Create LLM provider (lazy - only if enabled)
        self._provider = None

        if self.dry_run:
            logger.warning("AI_COPILOT_DRY_RUN=1 - no real LLM calls will be made")

    def _get_provider(self):
        """Lazy provider initialization."""
        if self._provider is None:
            # Use OpenAI for AI Co-Pilot (cost-effective)
            # In future, could respect config.llm_mode for consistency
            self._provider = create_provider(
                provider_type="openai",
                model=self.config.ai_copilot_model,
                timeout=self.config.ai_copilot_timeout_s,
            )
        return self._provider

    def reset_budget(self):
        """Reset call counter (called at start of each run)."""
        self.call_count = 0
        logger.debug(f"Budget reset. Max calls this run: {self.config.ai_copilot_max_calls_per_run}")

    def get_remaining_budget(self) -> int:
        """Get remaining LLM calls for this run."""
        return max(0, self.config.ai_copilot_max_calls_per_run - self.call_count)

    def generate_advisory_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.7,
        feature_name: str = "unknown",
        max_retries: int = 3,
    ) -> dict[str, Any] | None:
        """
        Generate advisory JSON output with budget gates and retries.

        This is the main entry point for all AI Co-Pilot LLM calls.

        Args:
            prompt: User prompt
            schema: Expected JSON schema
            temperature: Sampling temperature (0.0-1.0)
            feature_name: Name of calling feature (for logging)
            max_retries: Maximum retry attempts (default 3)

        Returns:
            Parsed JSON dict if successful, None if failed/budget exceeded

        Safety:
            - Never raises exceptions (returns None on failure)
            - Logs all failures for debugging
            - Respects budget gates
            - Respects dry-run mode
        """
        # Check if AI Co-Pilot is enabled
        if not self.config.ai_copilot_enabled:
            logger.debug(f"[{feature_name}] AI Co-Pilot disabled, skipping LLM call")
            return None

        # Check budget
        if self.call_count >= self.config.ai_copilot_max_calls_per_run:
            logger.warning(
                f"[{feature_name}] Budget exceeded: {self.call_count}/{self.config.ai_copilot_max_calls_per_run} calls"
            )
            return None

        # Increment call count (budget gate)
        self.call_count += 1
        logger.info(
            f"[{feature_name}] LLM call {self.call_count}/{self.config.ai_copilot_max_calls_per_run}"
        )

        # Handle dry-run mode (return mock data)
        if self.dry_run:
            logger.info(f"[{feature_name}] DRY RUN - returning mock data")
            return {"dry_run": True, "feature": feature_name}

        # Enforce max_output_tokens
        max_tokens = min(self.config.ai_copilot_max_output_tokens, 4096)

        # Retry logic with exponential backoff
        retry_delays = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s
        last_error = None

        for attempt in range(max_retries):
            try:
                provider = self._get_provider()
                start_time = time.time()

                result = provider.generate_structured_json(
                    prompt=prompt,
                    schema=schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                elapsed = time.time() - start_time
                logger.info(
                    f"[{feature_name}] LLM call succeeded in {elapsed:.2f}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )

                return result

            except TimeoutError as e:
                last_error = e
                logger.warning(
                    f"[{feature_name}] LLM timeout (attempt {attempt + 1}/{max_retries}): {e}"
                )

            except ValueError as e:
                # Schema validation error - likely malformed response
                last_error = e
                logger.warning(
                    f"[{feature_name}] Invalid response (attempt {attempt + 1}/{max_retries}): {e}"
                )

            except Exception as e:
                # Catch-all for provider errors (rate limits, network issues, etc.)
                last_error = e
                logger.warning(
                    f"[{feature_name}] LLM error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}: {e}"
                )

            # Exponential backoff before retry (except on last attempt)
            if attempt < max_retries - 1:
                delay = retry_delays[attempt]
                logger.debug(f"[{feature_name}] Retrying in {delay}s...")
                time.sleep(delay)

        # All retries exhausted - graceful degradation
        logger.error(
            f"[{feature_name}] All {max_retries} attempts failed. Last error: {last_error}"
        )
        return None

    def get_status(self) -> dict[str, Any]:
        """
        Get current client status for monitoring/debugging.

        Returns:
            Status dict with budget info, config, and feature flags
        """
        return {
            "enabled": self.config.ai_copilot_enabled,
            "dry_run": self.dry_run,
            "influence_decisions": self.config.ai_copilot_influence_decisions,
            "model": self.config.ai_copilot_model,
            "budget": {
                "max_calls_per_run": self.config.ai_copilot_max_calls_per_run,
                "calls_used": self.call_count,
                "calls_remaining": self.get_remaining_budget(),
            },
            "limits": {
                "max_output_tokens": self.config.ai_copilot_max_output_tokens,
                "timeout_s": self.config.ai_copilot_timeout_s,
            },
            "features": {
                "trade_rationale": self.config.ai_copilot_trade_rationale_enabled,
                "daily_journal": self.config.ai_copilot_daily_journal_enabled,
                "strategy_critique": self.config.ai_copilot_strategy_critique_enabled,
            },
        }
