"""Integration tests for /api/agents, /api/gateway, and /api/analytics endpoints."""

import pytest
from httpx import AsyncClient
from agents.provider_manager import ProviderManager, ProviderResponse


@pytest.mark.asyncio
async def test_agent_configuration_and_retrieval(async_client: AsyncClient):
    headers = {"X-User-ID": "test_user_api"}

    # 1. Configure Weak Agent
    weak_payload = {
        "agent_type": "weak",
        "provider": "groq",
        "api_key": "gsk_test_api_key_1234567890",
        "model_id": "llama-3.1-8b-instant",
        "temperature": 0.2,
        "max_tokens": 1024,
        "is_enabled": True,
    }
    res_weak = await async_client.post("/api/agents/configure", json=weak_payload, headers=headers)
    assert res_weak.status_code == 200
    data_weak = res_weak.json()
    assert data_weak["status"] == "configured"
    assert data_weak["agent"]["agent_type"] == "weak"
    assert data_weak["agent"]["masked_key"].startswith("gsk...")

    # 2. Configure Strong Agent
    strong_payload = {
        "agent_type": "strong",
        "provider": "openai",
        "api_key": "sk-proj-test_api_key_9876543210",
        "model_id": "gpt-4o",
        "temperature": 0.2,
        "max_tokens": 2048,
        "is_enabled": True,
    }
    res_strong = await async_client.post("/api/agents/configure", json=strong_payload, headers=headers)
    assert res_strong.status_code == 200
    data_strong = res_strong.json()
    assert data_strong["agent"]["agent_type"] == "strong"
    assert data_strong["agent"]["masked_key"].startswith("sk-...")

    # 3. Retrieve configurations
    res_get = await async_client.get("/api/agents/config", headers=headers)
    assert res_get.status_code == 200
    configs = res_get.json()["agents"]
    assert configs["weak"]["provider"] == "groq"
    assert configs["weak"]["model_id"] == "llama-3.1-8b-instant"
    assert "gsk_test_api_key" not in str(configs)  # Masked, never plaintext!
    assert configs["strong"]["provider"] == "openai"


@pytest.mark.asyncio
async def test_agent_connection_test(async_client: AsyncClient, monkeypatch):
    async def mock_test_conn(self, provider, api_key, model_id, base_url=None):
        return {
            "success": True,
            "latency_ms": 115,
            "message": f"Successfully verified connection to {provider} ({model_id})",
        }

    monkeypatch.setattr(ProviderManager, "test_connection", mock_test_conn)

    payload = {
        "provider": "groq",
        "api_key": "gsk_test_key_sample",
        "model_id": "llama-3.1-8b-instant",
    }
    res = await async_client.post("/api/agents/test", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["latency_ms"] == 115


@pytest.mark.asyncio
async def test_gateway_execute_and_telemetry(async_client: AsyncClient, monkeypatch):
    headers = {"X-User-ID": "test_user_exec"}

    # Mock provider execution
    async def mock_execute(self, provider, api_key, model_id, messages, **kwargs):
        return ProviderResponse(
            content=f"Execution output from {provider} model {model_id}",
            prompt_tokens=18,
            completion_tokens=32,
            total_tokens=50,
            model=model_id,
            provider=provider,
            latency_ms=180,
        )

    monkeypatch.setattr(ProviderManager, "execute", mock_execute)

    # 1. Setup credentials for user
    await async_client.post(
        "/api/agents/configure",
        json={"agent_type": "weak", "provider": "groq", "api_key": "gsk_12345678", "model_id": "llama-3.1-8b-instant"},
        headers=headers,
    )
    await async_client.post(
        "/api/agents/configure",
        json={"agent_type": "strong", "provider": "openai", "api_key": "sk_12345678", "model_id": "gpt-4o"},
        headers=headers,
    )

    # 2. Execute Simple Prompt via Adaptive Mode
    res1 = await async_client.post(
        "/api/gateway/execute",
        json={"prompt": "What is Python?", "mode": "adaptive"},
        headers=headers,
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["success"] is True
    assert data1["agent"] == "weak"
    assert data1["provider"] == "groq"
    assert "llama-3.1-8b-instant" in data1["model"]
    assert "Execution output" in data1["response"]
    assert data1["cost"] > 0

    # 3. Execute Complex Prompt via Adaptive Mode
    res2 = await async_client.post(
        "/api/gateway/execute",
        json={"prompt": "Design a scalable distributed banking architecture with two-phase commit.", "mode": "adaptive"},
        headers=headers,
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["success"] is True
    assert data2["agent"] == "strong"
    assert data2["provider"] == "openai"
    assert "gpt-4o" in data2["model"]

    # 4. Manual override
    res3 = await async_client.post(
        "/api/gateway/execute",
        json={"prompt": "Hello there", "mode": "strong"},
        headers=headers,
    )
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["agent"] == "strong"

    # 5. Check History
    hist_res = await async_client.get("/api/gateway/history?limit=10")
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) >= 3

    # 6. Check Analytics Overview
    analytics_res = await async_client.get("/api/analytics/overview")
    assert analytics_res.status_code == 200
    analytics = analytics_res.json()
    assert analytics["total_requests"] >= 3
    assert analytics["weak_agent_requests"] >= 1
    assert analytics["strong_agent_requests"] >= 2
    assert analytics["cost_savings_pct"] >= 0.0

    # 7. Check Analytics Usage
    usage_res = await async_client.get("/api/analytics/usage")
    assert usage_res.status_code == 200
    usage = usage_res.json()
    assert "overview" in usage
    assert "history" in usage


@pytest.mark.asyncio
async def test_gateway_streaming_sse(async_client: AsyncClient, monkeypatch):
    headers = {"X-User-ID": "test_user_stream"}

    async def mock_stream_execute(self, provider, api_key, model_id, messages, **kwargs):
        yield {"choices": [{"delta": {"content": "Streamed "}}]}
        yield {"choices": [{"delta": {"content": "real response."}}]}

    monkeypatch.setattr(ProviderManager, "stream_execute", mock_stream_execute)

    await async_client.post(
        "/api/agents/configure",
        json={"agent_type": "weak", "provider": "groq", "api_key": "gsk_12345678", "model_id": "llama-3.1-8b-instant"},
        headers=headers,
    )

    res = await async_client.post(
        "/api/gateway/stream",
        json={"prompt": "What is Python?", "mode": "adaptive"},
        headers=headers,
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    text = res.text
    assert "routing" in text
    assert "token" in text
    assert "Streamed" in text
    assert "done" in text
