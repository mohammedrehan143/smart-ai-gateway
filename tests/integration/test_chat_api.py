"""Integration tests for POST /v1/chat endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_completion_success(async_client: AsyncClient):
    payload = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello from the test suite!"},
        ],
        "routing": {
            "policy": "adaptive",
        },
        "parameters": {
            "temperature": 0.2,
            "max_output_tokens": 500,
        },
    }

    resp = await async_client.post(
        "/v1/chat",
        json=payload,
        headers={"X-Request-ID": "test-req-001"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["object"] == "gateway.completion"
    assert data["id"].startswith("req_")
    assert data["trace_id"].startswith("tr_")
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert "Mock completion response" in data["choices"][0]["message"]["content"]
    assert data["usage"]["total_tokens"] > 0
    assert data["routing"]["policy"] == "adaptive"
    assert data["cached"] is False


@pytest.mark.asyncio
async def test_chat_completion_validation_error(async_client: AsyncClient):
    # Empty messages list should fail schema validation (422)
    payload = {
        "messages": [],
    }
    resp = await async_client.post("/v1/chat", json=payload)
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert data["error"]["type"] == "invalid_request"


@pytest.mark.asyncio
async def test_chat_completions_alias_success(async_client: AsyncClient):
    payload = {
        "messages": [
            {"role": "user", "content": "Testing OpenAI-compatible completions endpoint"},
        ],
    }
    resp = await async_client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "gateway.completion"
