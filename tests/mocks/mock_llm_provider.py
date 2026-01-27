"""Mock LLM provider for testing (no network calls)."""

from src.app.llm.providers.base import LLMProvider


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing without network calls."""

    def __init__(self, provider_name: str = "mock", responses: dict | None = None):
        """Initialize mock provider.

        Args:
            provider_name: Provider name to return
            responses: Pre-configured responses (defaults to sample proposal)
        """
        self.provider_name = provider_name
        self.responses = responses or {}
        self.call_count = 0
        self.call_history = []

    def generate_structured_json(
        self,
        prompt: str,
        schema: dict,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict:
        """Return deterministic mock response.

        Args:
            prompt: User prompt (recorded but not used)
            schema: Expected schema (recorded but not used)
            temperature: Temperature (recorded but not used)
            max_tokens: Max tokens (recorded but not used)

        Returns:
            Pre-configured response or default sample
        """
        self.call_count += 1
        self.call_history.append(
            {
                "prompt": prompt,
                "schema": schema,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )

        # Return pre-configured response if available
        if self.responses:
            return self.responses

        # Default response (for legacy tests expecting proposals)
        return {
            "proposals": [
                {
                    "sector_name": "mega_cap_tech",
                    "recommended_enabled": True,
                    "confidence": 0.85,
                    "rationale": "Test rationale for enabling tech sector",
                    "supporting_headline_numbers": [1, 2],
                }
            ]
        }

    def get_provider_name(self) -> str:
        """Return provider name."""
        return self.provider_name
