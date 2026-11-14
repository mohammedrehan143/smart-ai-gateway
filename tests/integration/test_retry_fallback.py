"""Integration tests for retry and fallback behaviors."""

from typing import List, Optional
import pytest
from httpx import AsyncClient
from app.api.deps import get_orchestrator
from app.core.config import settings
from app.core.errors import ProviderServerError
from app.domain.entities import ChatMessage, GenerationParameters, NormalizedCompletion
from app.main import app
from app.providers.base import BaseProviderAdapter
from app.repositories.sqlite import SqliteTraceRepository
from app.services.orchestrator import ChatOrchestrator


class FlakyRetryAdapter(BaseProviderAdapter):
    """Fails on first attempt, succeeds on second."""

    def __init__(self):
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate(
        self,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
        model_alias: str,
        timeout_seconds: float,
        tools: Optional[list] = None,
    ) -> NormalizedCompletion:
        self.call_count += 1
        if self.call_count == 1:
            raise ProviderServerError("Transient 500 error on attempt 1")
        return NormalizedCompletion(
            content="Recovered after retry!",
            finish_reason="stop",
            provider="mock",
            model_alias=model_alias,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )


class FallbackRequiredAdapter(BaseProviderAdapter):
    """Always fails for mock-cheap, succeeds for mock-strong (fallback)."""

    def __init__(self):
        self.attempts = []

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate(
        self,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
        model_alias: str,
        timeout_seconds: float,
        tools: Optional[list] = None,
    ) -> NormalizedCompletion:
        self.attempts.append(model_alias)
        if model_alias == settings.CHEAP_MODEL_ALIAS:
            raise ProviderServerError("Primary model completely unavailable")
        return NormalizedCompletion(
            content="Success from fallback model!",
            finish_reason="stop",
            provider="mock",
            model_alias=model_alias,
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
        )


@pytest.mark.asyncio
async def test_retry_on_transient_failure(async_client: AsyncClient, test_repo: SqliteTraceRepository):
    flaky_adapter = FlakyRetryAdapter()
    orch = ChatOrchestrator(repository=test_repo, default_adapter=flaky_adapter)
    app.dependency_overrides[get_orchestrator] = lambda: orch

    payload = {"messages": [{"role": "user", "content": "Trigger retry."}]}
    resp = await async_client.post("/v1/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "Recovered after retry!" in data["choices"][0]["message"]["content"]

    # Verify 2 attempts were persisted
    attempts = await test_repo.get_attempts(data["id"])
    assert len(attempts) == 2
    assert attempts[0].status == "failure"
    assert attempts[1].status == "success"


@pytest.mark.asyncio
async def test_fallback_to_alternate_model(async_client: AsyncClient, test_repo: SqliteTraceRepository):
    fallback_adapter = FallbackRequiredAdapter()
    orch = ChatOrchestrator(repository=test_repo, default_adapter=fallback_adapter)
    app.dependency_overrides[get_orchestrator] = lambda: orch

    payload = {
        "messages": [{"role": "user", "content": "Trigger fallback."}],
        "routing": {"policy": "always_cheap"},
    }
    resp = await async_client.post("/v1/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["routing"]["fallback_used"] is True
    assert data["model"] == settings.FALLBACK_MODEL_ALIAS
    assert "fallback model" in data["choices"][0]["message"]["content"]
