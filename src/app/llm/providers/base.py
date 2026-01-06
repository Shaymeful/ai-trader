"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate_structured_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        """
        Generate structured JSON response from LLM.

        Args:
            prompt: User prompt
            schema: Expected JSON schema (for validation)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum response tokens

        Returns:
            Parsed JSON dict matching schema

        Raises:
            ValueError: If response doesn't match schema
            TimeoutError: If request times out
            Exception: For other provider errors
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider name (e.g., 'openai', 'anthropic')."""
        pass
