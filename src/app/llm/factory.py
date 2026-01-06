"""Factory for creating LLM provider instances."""

from typing import Literal

from .providers.base import LLMProvider

ProviderMode = Literal["primary_fallback", "ensemble", "openai_only", "anthropic_only"]
ProviderType = Literal["openai", "anthropic"]


def create_provider(
    provider_type: ProviderType,
    model: str | None = None,
    api_key: str | None = None,
    timeout: int = 30,
) -> LLMProvider:
    """Create a single provider instance.

    Args:
        provider_type: Type of provider ("openai" or "anthropic")
        model: Optional model name override
        api_key: Optional API key override
        timeout: Request timeout in seconds

    Returns:
        Configured provider instance

    Raises:
        ValueError: If provider_type is invalid
    """
    if provider_type == "openai":
        # Lazy import to avoid requiring openai package when not used
        from .providers.openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=api_key, model=model or "gpt-4-turbo-preview", timeout=timeout
        )
    elif provider_type == "anthropic":
        # Lazy import to avoid requiring anthropic package when not used
        from .providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=api_key, model=model or "claude-3-5-sonnet-20241022", timeout=timeout
        )
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")


def get_providers_for_mode(
    mode: ProviderMode,
    primary: ProviderType = "openai",
    openai_model: str | None = None,
    anthropic_model: str | None = None,
    timeout: int = 30,
) -> tuple[LLMProvider, ...]:
    """Get provider instances for a given mode.

    Args:
        mode: Provider mode
        primary: Primary provider for primary_fallback mode
        openai_model: OpenAI model override
        anthropic_model: Anthropic model override
        timeout: Request timeout in seconds

    Returns:
        Tuple of providers (primary, [secondary])

    Raises:
        ValueError: If mode is invalid
    """
    if mode == "openai_only":
        return (create_provider("openai", openai_model, timeout=timeout),)

    elif mode == "anthropic_only":
        return (create_provider("anthropic", anthropic_model, timeout=timeout),)

    elif mode == "primary_fallback":
        if primary == "openai":
            return (
                create_provider("openai", openai_model, timeout=timeout),
                create_provider("anthropic", anthropic_model, timeout=timeout),
            )
        else:
            return (
                create_provider("anthropic", anthropic_model, timeout=timeout),
                create_provider("openai", openai_model, timeout=timeout),
            )

    elif mode == "ensemble":
        return (
            create_provider("openai", openai_model, timeout=timeout),
            create_provider("anthropic", anthropic_model, timeout=timeout),
        )

    else:
        raise ValueError(f"Unknown mode: {mode}")
