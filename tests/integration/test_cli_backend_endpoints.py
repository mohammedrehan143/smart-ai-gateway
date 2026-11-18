"""Integration tests for CLI backend endpoints (models, analytics, routing, auth, streaming)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_verify_endpoint(async_client: AsyncClient):
    resp = await async_client.get("/v1/auth/verify")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "authenticated"
    assert "gateway_version" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_models_catalog_endpoint(async_client: AsyncClient):
    resp = await async_client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert data["total"] >= 2
    model_aliases = [m["alias"] for m in data["data"]]
    assert "mock-cheap" in model_aliases
    assert "mock-strong" in model_aliases
    # Check rate card pricing
    cheap_model = next(m for m in data["data"] if m["alias"] == "mock-cheap")
    assert cheap_model["pricing"]["input_rate_per_million"] == 0.15
    assert cheap_model["pricing"]["currency"] == "USD"


@pytest.mark.asyncio
async def test_analytics_usage_and_cost(async_client: AsyncClient):
    # Perform a chat request first to populate telemetry
    chat_payload = {
        "messages": [{"role": "user", "content": "What is Python asyncio?"}],
        "routing": {"policy": "adaptive"},
    }
    chat_resp = await async_client.post("/v1/chat", json=chat_payload)
    assert chat_resp.status_code == 200

    # Test usage analytics
    usage_resp = await async_client.get("/v1/analytics/usage")
    assert usage_resp.status_code == 200
    usage_data = usage_resp.json()
    assert usage_data["total_requests"] >= 1
    assert "policy_breakdown" in usage_data
    assert "recent_requests" in usage_data

    # Test cost analytics
    cost_resp = await async_client.get("/v1/analytics/cost")
    assert cost_resp.status_code == 200
    cost_data = cost_resp.json()
    assert "total_spend" in cost_data
    assert cost_data["currency"] == "USD"


@pytest.mark.asyncio
async def test_routing_decisions_inspection(async_client: AsyncClient):
    # Perform a request first to generate a routing decision
    await async_client.post(
        "/v1/chat",
        json={
            "messages": [
                {"role": "user", "content": "Explain quicksort in Python:\n\n```python\ndef quicksort(): pass\n```"}
            ]
        },
    )

    resp = await async_client.get("/v1/routing/decisions?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "decisions" in data
    assert len(data["decisions"]) >= 1
    first_dec = data["decisions"][0]
    assert "trace_id" in first_dec
    assert "tier" in first_dec
    assert "reason" in first_dec


@pytest.mark.asyncio
async def test_chat_streaming_sse(async_client: AsyncClient):
    payload = {
        "messages": [{"role": "user", "content": "Tell me a short greeting"}],
        "stream": True,
    }
    resp = await async_client.post("/v1/chat", json=payload)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    content = resp.text
    assert "data: " in content
    assert "chat.completion.chunk" in content
    assert "[DONE]" in content
