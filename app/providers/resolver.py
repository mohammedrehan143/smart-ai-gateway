"""Dynamic provider adapter resolving between real hosted credentials, BYOK keys, and mock adapters."""

from __future__ import annotations

import os
import time
from typing import List, Optional
from app.core.config import settings
from app.domain.byok import default_byok_manager
from app.domain.circuit_breaker import default_circuit_registry
from app.domain.entities import ChatMessage, GenerationParameters, NormalizedCompletion
from app.domain.registry import registry
from app.providers.base import BaseProviderAdapter
from app.providers.mock import MockProviderAdapter
from app.providers.openai_compatible import OpenAICompatibleAdapter


def is_mock_mode_explicitly_enabled() -> bool:
    """Determines whether mock execution mode is explicitly enabled (test suite or explicit flag)."""
    import os, sys
    if os.environ.get("APP_ENV") == "test" or "pytest" in sys.modules:
        return True
    if os.environ.get("ENABLE_MOCK_GATEWAY", "").lower() in ("true", "1", "yes"):
        return True
    try:
        from app.core.config import settings
        if getattr(settings, "ENABLE_MOCK_GATEWAY", False):
            return True
    except Exception:
        pass
    return False


def _is_real_key(key: Optional[str]) -> bool:
    """Checks if a credential string is a real upstream API key rather than dummy test data."""
    if not key or len(key.strip()) < 8:
        return False
    k = key.strip().lower()
    if any(dummy in k for dummy in ("sample", "mock", "dummy", "fake", "placeholder", "test")):
        return False
    return True


class RealAgentAdapter(BaseProviderAdapter):
    """Executes real AI models via the unified ProviderManager using configured BYOK credentials."""

    def __init__(self, provider: str, api_key: str, model_id: str, base_url: Optional[str] = None):
        self._provider = provider
        self._api_key = api_key
        self._model_id = model_id
        self._base_url = base_url

    @property
    def provider_name(self) -> str:
        return self._provider

    async def generate(
        self,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
        model_alias: str,
        timeout_seconds: float,
        tools: Optional[list] = None,
    ) -> NormalizedCompletion:
        from agents.provider_manager import default_provider_manager

        formatted_messages = [{"role": m.role, "content": m.content} for m in messages]
        resp = await default_provider_manager.execute(
            provider=self._provider,
            api_key=self._api_key,
            model_id=self._model_id,
            messages=formatted_messages,
            temperature=parameters.temperature,
            max_tokens=parameters.max_output_tokens or 1024,
            base_url=self._base_url,
            timeout_seconds=timeout_seconds,
        )

        return NormalizedCompletion(
            content=resp.content,
            finish_reason="stop",
            provider=self._provider,
            model_alias=self._model_id,
            provider_request_id=f"real_{int(time.time()*1000)}",
            input_tokens=resp.prompt_tokens,
            output_tokens=resp.completion_tokens,
            total_tokens=resp.total_tokens,
            raw_usage_available=True,
            is_mock=False,
        )


class DynamicProviderAdapter(BaseProviderAdapter):
    """Dynamically routes upstream requests to appropriate BYOK credentials, system keys, or mock adapter."""

    def __init__(self):
        self._mock_adapter = MockProviderAdapter()

    @property
    def provider_name(self) -> str:
        return "dynamic_gateway"

    def _resolve_adapter(self, model_alias: str, user_id: Optional[str] = None) -> BaseProviderAdapter:
        effective_user_id = user_id or "default_user"
        meta = registry.get_model(model_alias)
        tier = meta.tier if meta else ("cheap" if "cheap" in model_alias else "strong")

        # 1. Check Dual-Agent Configuration from CredentialManager (Weak / Strong Agents)
        try:
            from agents.credential_manager import default_credential_manager

            # Priority 1: Match by tier
            target_agent = "weak" if tier == "cheap" else "strong"
            cfg = default_credential_manager.get_agent_config(effective_user_id, target_agent)

            # If target agent not configured, check the other agent as fallback
            if not cfg or not cfg.is_enabled or not cfg.encrypted_key:
                other_agent = "strong" if target_agent == "weak" else "weak"
                cfg = default_credential_manager.get_agent_config(effective_user_id, other_agent)

            if cfg and cfg.is_enabled and cfg.encrypted_key:
                raw_key = cfg.get_plaintext_key()
                if _is_real_key(raw_key):
                    return RealAgentAdapter(
                        provider=cfg.provider,
                        api_key=raw_key,
                        model_id=cfg.model_id,
                        base_url=cfg.base_url,
                    )
        except Exception:
            pass

        # 2. Check environment variables (GROQ_API_KEY, OPENAI_API_KEY)
        groq_env_key = os.environ.get("GROQ_API_KEY")
        if _is_real_key(groq_env_key) and (tier == "cheap" or not os.environ.get("OPENAI_API_KEY")):
            return RealAgentAdapter(
                provider="groq",
                api_key=groq_env_key,
                model_id="openai/gpt-oss-120b",
                base_url="https://api.groq.com/openai/v1",
            )

        openai_env_key = os.environ.get("OPENAI_API_KEY")
        if _is_real_key(openai_env_key):
            return RealAgentAdapter(
                provider="openai",
                api_key=openai_env_key,
                model_id="gpt-4o" if tier == "strong" else "gpt-4o-mini",
            )

        # 3. Check legacy BYOK credentials
        if user_id:
            provider = meta.provider if meta else "openai"
            user_key = default_byok_manager.get_plaintext_key(user_id, provider)
            if user_key:
                user_base_url = default_byok_manager.get_base_url(user_id, provider) or settings.PROVIDER_BASE_URL
                return OpenAICompatibleAdapter(api_key=user_key, base_url=user_base_url)

        # 4. Check dedicated cheap model credential
        if model_alias == settings.CHEAP_MODEL_ALIAS:
            api_key = settings.CHEAP_PROVIDER_API_KEY or settings.PROVIDER_API_KEY
            base_url = settings.CHEAP_PROVIDER_BASE_URL or settings.PROVIDER_BASE_URL
            if api_key:
                return OpenAICompatibleAdapter(api_key=api_key, base_url=base_url)

        # 5. Check dedicated strong model credential
        if model_alias in (settings.STRONG_MODEL_ALIAS, settings.FALLBACK_MODEL_ALIAS):
            api_key = settings.STRONG_PROVIDER_API_KEY or settings.PROVIDER_API_KEY
            base_url = settings.STRONG_PROVIDER_BASE_URL or settings.PROVIDER_BASE_URL
            if api_key:
                return OpenAICompatibleAdapter(api_key=api_key, base_url=base_url)

        # 6. Check general provider key
        if settings.PROVIDER_API_KEY:
            return OpenAICompatibleAdapter(
                api_key=settings.PROVIDER_API_KEY,
                base_url=settings.PROVIDER_BASE_URL,
            )

        # 7. Check if mock mode is explicitly enabled
        if is_mock_mode_explicitly_enabled():
            return self._mock_adapter

        # In production / live execution, do NOT silently fall back to mock mode!
        from app.core.errors import ProviderAuthError
        target_agent = "weak" if tier == "cheap" else "strong"
        raise ProviderAuthError(
            f"No live API key configured for {target_agent} agent ({model_alias}). "
            f"Please configure your API key in Agent Settings (http://localhost:8000) or set GROQ_API_KEY / OPENAI_API_KEY in your environment."
        )

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
