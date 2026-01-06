"""LLM provider implementations."""

from .base import LLMProvider

# Lazy imports to avoid requiring openai/anthropic packages when not needed
__all__ = ["LLMProvider", "OpenAIProvider", "AnthropicProvider"]


def __getattr__(name):
    """Lazy import providers to avoid requiring packages when not needed."""
    if name == "OpenAIProvider":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider
    elif name == "AnthropicProvider":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
