"""Anthropic Claude API provider implementation."""

import json
import os

from anthropic import Anthropic

from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-3-5-sonnet-20241022",
        timeout: int = 30,
    ):
        """Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Model to use (default: claude-3-5-sonnet-20241022)
            timeout: Request timeout in seconds (default: 30)

        Raises:
            ValueError: If API key is not found
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.timeout = timeout

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found")

        self.client = Anthropic(
            api_key=self.api_key,
            timeout=timeout,
        )

    def generate_structured_json(
        self,
        prompt: str,
        schema: dict,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict:
        """Generate JSON using Claude prompt engineering.

        Args:
            prompt: User prompt
            schema: Expected JSON schema (appended to prompt)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum response tokens

        Returns:
            Parsed JSON dict

        Raises:
            Exception: If Anthropic API call fails
        """
        # Append JSON schema instruction
        enhanced_prompt = f"""{prompt}

Please respond with ONLY valid JSON matching this schema:
{json.dumps(schema, indent=2)}

Do not include any other text."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": enhanced_prompt}],
            )

            content = response.content[0].text

            # Extract JSON from markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            return json.loads(content)

        except Exception as e:
            raise Exception(f"Anthropic API error: {e}") from e

    def get_provider_name(self) -> str:
        """Return provider name."""
        return "anthropic"
