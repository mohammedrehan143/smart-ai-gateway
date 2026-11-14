"""Dynamic provider adapter resolving between real hosted credentials, BYOK keys, and mock adapters."""

from __future__ import annotations

from typing import List, Optional
from app.core.config import settings
from app.domain.byok import default_byok_manager
from app.domain.circuit_breaker import default_circuit_registry
from app.domain.entities import ChatMessage, GenerationParameters, NormalizedCompletion
from app.domain.registry import registry
from app.providers.base import BaseProviderAdapter
from app.providers.mock import MockProviderAdapter
from app.providers.openai_compatible import OpenAICompatibleAdapter


class DynamicProviderAdapter(BaseProviderAdapter):
    """Dynamically routes upstream requests to appropriate BYOK credentials, system keys, or mock adapter."""

    def __init__(self):
        self._mock_adapter = MockProviderAdapter()

    @property
    def provider_name(self) -> str:
        return "dynamic_gateway"

    def _resolve_adapter(self, model_alias: str, user_id: Optional[str] = None) -> BaseProviderAdapter:
        meta = registry.get_model(model_alias)
        provider = meta.provider if meta else "openai"

        # 1. Check user-specific BYOK credentials first
        if user_id:
            user_key = default_byok_manager.get_plaintext_key(user_id, provider)
            if user_key:
                user_base_url = default_byok_manager.get_base_url(user_id, provider) or settings.PROVIDER_BASE_URL
                return OpenAICompatibleAdapter(api_key=user_key, base_url=user_base_url)

        # 2. Check dedicated cheap model credential
        if model_alias == settings.CHEAP_MODEL_ALIAS:
            api_key = settings.CHEAP_PROVIDER_API_KEY or settings.PROVIDER_API_KEY
            base_url = settings.CHEAP_PROVIDER_BASE_URL or settings.PROVIDER_BASE_URL
            if api_key:
                return OpenAICompatibleAdapter(api_key=api_key, base_url=base_url)

        # 3. Check dedicated strong model credential
        if model_alias in (settings.STRONG_MODEL_ALIAS, settings.FALLBACK_MODEL_ALIAS):
            api_key = settings.STRONG_PROVIDER_API_KEY or settings.PROVIDER_API_KEY
            base_url = settings.STRONG_PROVIDER_BASE_URL or settings.PROVIDER_BASE_URL
            if api_key:
                return OpenAICompatibleAdapter(api_key=api_key, base_url=base_url)

        # 4. Check general provider key
        if settings.PROVIDER_API_KEY:
            return OpenAICompatibleAdapter(
                api_key=settings.PROVIDER_API_KEY,
                base_url=settings.PROVIDER_BASE_URL,
            )

        # 5. Default to deterministic mock adapter
        return self._mock_adapter

    async def generate(
        self,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
        model_alias: str,
        timeout_seconds: float,
        tools: Optional[list] = None,
        user_id: Optional[str] = None,
    ) -> NormalizedCompletion:
        adapter = self._resolve_adapter(model_alias, user_id=user_id)
        try:
            res = await adapter.generate(
                messages=messages,
                parameters=parameters,
                model_alias=model_alias,
                timeout_seconds=timeout_seconds,
                tools=tools,
            )
            default_circuit_registry.record_outcome(model_alias, success=True)
            return res
        except Exception as exc:
            default_circuit_registry.record_outcome(model_alias, success=False, error=exc)
            raise exc
