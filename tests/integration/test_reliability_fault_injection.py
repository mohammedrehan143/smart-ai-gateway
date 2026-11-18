"""Reliability and fault injection tests for timeouts, outages, 429 rate limits, and concurrency."""

import asyncio
import pytest
from httpx import AsyncClient
from app.api.deps import get_orchestrator
from app.core.errors import ProviderAuthError, ProviderServerError, RateLimitError, RequestTimeoutError
from app.domain.entities import NormalizedCompletion
from app.main import app
from app.providers.base import BaseProviderAdapter
from app.repositories.sqlite import SqliteTraceRepository
from app.services.orchestrator import ChatOrchestrator


class FaultInjectionAdapter(BaseProviderAdapter):
    """Adapter designed for injecting specific upstream failure modes."""

    def __init__(self, failure_mode: str, retry_after: float = 2.0):
        self.failure_mode = failure_mode
        self.retry_after = retry_after
        self.attempt_count = 0

    @property
    def provider_name(self) -> str:
        return "fault_injection"

    async def generate(
        self,
        messages,
        parameters,
        model_alias,
        timeout_seconds,
        tools=None,
        user_id=None,
        **kwargs,
    ) -> NormalizedCompletion:
        self.attempt_count += 1
        if self.failure_mode == "timeout":
            raise RequestTimeoutError("Upstream provider gateway timeout (504)")
        elif self.failure_mode == "outage":
            raise ProviderServerError("Upstream provider 503 Service Unavailable")
        elif self.failure_mode == "invalid_key":
            raise ProviderAuthError("Invalid upstream API key or revoked credential (401)")
        elif self.failure_mode == "rate_limit":
            raise RateLimitError("Upstream provider 429 Too Many Requests", retry_after_s=self.retry_after)

        return NormalizedCompletion(
            content="Healthy response",
            finish_reason="stop",
            provider="fault_injection",
            model_alias=model_alias,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )


@pytest.mark.asyncio
async def test_provider_timeout_exhaustion(async_client: AsyncClient, test_repo: SqliteTraceRepository):
    """Verify that timeout errors are tracked and cleanly return 504 / ProviderUnavailableError."""
    timeout_adapter = FaultInjectionAdapter("timeout")
    orch = ChatOrchestrator(repository=test_repo, default_adapter=timeout_adapter)
    app.dependency_overrides[get_orchestrator] = lambda: orch

    resp = await async_client.post("/v1/chat", json={"messages": [{"role": "user", "content": "Timeout test"}]})
    assert resp.status_code in (503, 504)
    data = resp.json()
    assert "error" in data


@pytest.mark.asyncio
async def test_provider_outage_fallback_exhaustion(async_client: AsyncClient, test_repo: SqliteTraceRepository):
    """Verify that provider outages cleanly report provider unavailable errors."""
    outage_adapter = FaultInjectionAdapter("outage")
    orch = ChatOrchestrator(repository=test_repo, default_adapter=outage_adapter)
    app.dependency_overrides[get_orchestrator] = lambda: orch

    resp = await async_client.post("/v1/chat", json={"messages": [{"role": "user", "content": "Outage test"}]})
    assert resp.status_code in (502, 503)
    data = resp.json()
    assert data["error"]["type"] in ("provider_unavailable", "provider_server_error")


@pytest.mark.asyncio
async def test_invalid_api_key_is_not_retried(async_client: AsyncClient, test_repo: SqliteTraceRepository):
    """Verify that permanent auth errors (401) are non-retryable and fail fast."""
    auth_adapter = FaultInjectionAdapter("invalid_key")
    orch = ChatOrchestrator(repository=test_repo, default_adapter=auth_adapter)
    app.dependency_overrides[get_orchestrator] = lambda: orch

    resp = await async_client.post(
        "/v1/chat",
        json={
            "messages": [{"role": "user", "content": "Auth error test"}],
            "routing": {"policy": "always_cheap"},
        },
    )
    assert resp.status_code in (503, 401)
    # Auth error should fail immediately without per-model retries (each candidate tried once, total 2 candidates)
    assert auth_adapter.attempt_count == 2


@pytest.mark.asyncio
async def test_concurrent_requests_handling(async_client: AsyncClient):
    """Verify that 20 concurrent chat completions execute and complete without SQLite database locks."""
    # Reset overrides to default
    app.dependency_overrides.pop(get_orchestrator, None)

    async def make_request(i: int):
        payload = {
            "messages": [{"role": "user", "content": f"Concurrent test request #{i}"}],
            "routing": {"policy": "always_cheap"},
        }
        return await async_client.post("/v1/chat", json=payload)

    # Launch 20 concurrent requests
    responses = await asyncio.gather(*[make_request(i) for i in range(20)])
    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
    for r in responses:
        data = r.json()
        assert data["object"] == "gateway.completion"
        assert len(data["choices"]) == 1
