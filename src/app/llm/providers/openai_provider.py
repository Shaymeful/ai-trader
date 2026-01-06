"""OpenAI API provider implementation."""

import json
import os

from openai import OpenAI

from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4-turbo-preview",
        base_url: str | None = None,
        timeout: int = 30,
    ):
        """Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model to use (default: gpt-4-turbo-preview)
            base_url: Optional base URL override
            timeout: Request timeout in seconds (default: 30)

        Raises:
            ValueError: If API key is not found
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.timeout = timeout

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url,
            timeout=timeout,
        )

    def generate_structured_json(
        self,
        prompt: str,
        schema: dict,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict:
        """Generate JSON using OpenAI JSON mode.

        Args:
            prompt: User prompt
            schema: Expected JSON schema (informational)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum response tokens

        Returns:
            Parsed JSON dict

        Raises:
            Exception: If OpenAI API call fails
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},  # JSON mode
            )

            content = response.choices[0].message.content
            if content is None:
                raise ValueError("OpenAI returned empty response")

            return json.loads(content)

        except Exception as e:
            raise Exception(f"OpenAI API error: {e}") from e

    def get_provider_name(self) -> str:
        """Return provider name."""
        return "openai"
