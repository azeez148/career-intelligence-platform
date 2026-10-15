"""AI provider integrations behind the provider-independent `AIProvider` interface."""

from app.core.config import Settings
from app.integrations.ai.provider import AIProvider, DisabledProvider


def provider_from_settings(settings: Settings) -> AIProvider:
    if not settings.ai_enabled:
        return DisabledProvider()
    from app.integrations.ai.openrouter import OpenRouterProvider

    assert settings.openrouter_api_key is not None and settings.ai_model is not None
    return OpenRouterProvider(
        api_key=settings.openrouter_api_key.get_secret_value(),
        model=settings.ai_model,
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.ai_timeout_seconds,
        max_output_tokens=settings.ai_max_output_tokens,
    )
