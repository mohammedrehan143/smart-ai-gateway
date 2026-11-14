"""Dynamic provider adapter resolving between real hosted credentials and mock adapters."""

from __future__ import annotations

from typing import List, Optional
from app.core.config import settings
from app.domain.entities import ChatMessage, GenerationParameters, NormalizedCompletion
from app.providers.base import BaseProviderAdapter
from app.providers.mock import MockProviderAdapter
from app.providers.openai_compatible import OpenAICompatibleAdapter


class DynamicProviderAdapter(BaseProviderAdapter):
    """Dynamically routes upstream requests to appropriate credentials or mock adapter."""

    def __init__(self):
        self._mock_adapter = MockProviderAdapter()

    @property
    def provider_name(self) -> str:
        return "dynamic_gateway"

    def _resolve_adapter(self, model_alias: str) -> BaseProviderAdapter:
        # 1. Check if model is the cheap model
        if model_alias == settings.CHEAP_MODEL_ALIAS:
            api_key = settings.CHEAP_PROVIDER_API_KEY or settings.PROVIDER_API_KEY
            base_url = settings.CHEAP_PROVIDER_BASE_URL or settings.PROVIDER_BASE_URL
            if api_key:
                return OpenAICompatibleAdapter(api_key=api_key, base_url=base_url)

        # 2. Check if model is the strong model or fallback
        if model_alias in (settings.STRONG_MODEL_ALIAS, settings.FALLBACK_MODEL_ALIAS):
            api_key = settings.STRONG_PROVIDER_API_KEY or settings.PROVIDER_API_KEY
            base_url = settings.STRONG_PROVIDER_BASE_URL or settings.PROVIDER_BASE_URL
            if api_key:
                return OpenAICompatibleAdapter(api_key=api_key, base_url=base_url)

        # 3. Check general provider key
        if settings.PROVIDER_API_KEY:
            return OpenAICompatibleAdapter(
                api_key=settings.PROVIDER_API_KEY,
                base_url=settings.PROVIDER_BASE_URL,
            )

        # 4. Default to mock adapter if no hosted keys are configured
        return self._mock_adapter

    async def generate(
        self,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
        model_alias: str,
        timeout_seconds: float,
        tools: Optional[list] = None,
    ) -> NormalizedCompletion:
        adapter = self._resolve_adapter(model_alias)
        return await adapter.generate(
            messages=messages,
            parameters=parameters,
            model_alias=model_alias,
            timeout_seconds=timeout_seconds,
            tools=tools,
        )
