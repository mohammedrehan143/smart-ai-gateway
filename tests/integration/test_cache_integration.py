"""Integration tests for response caching on POST /v1/chat."""

import pytest
from httpx import AsyncClient
from app.services.cache_service import default_cache_service


@pytest.mark.asyncio
async def test_cache_hit_on_duplicate_request(async_client: AsyncClient):
    default_cache_service.clear()

    payload = {
        "messages": [
            {"role": "user", "content": "What is the capital of France?"},
        ],
        "parameters": {
            "temperature": 0.0,
            "max_output_tokens": 100,
        },
    }

    # First request: Cache Miss
    resp1 = await async_client.post("/v1/chat", json=payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["cached"] is False

    # Second request: Cache Hit
    resp2 = await async_client.post("/v1/chat", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cached"] is True
    assert data2["choices"][0]["message"]["content"] == data1["choices"][0]["message"]["content"]
    assert data2["routing"]["reason"] == "Served from cache"


@pytest.mark.asyncio
async def test_cache_bypass_on_high_temperature(async_client: AsyncClient):
    default_cache_service.clear()

    payload = {
        "messages": [
            {"role": "user", "content": "Generate a creative story."},
        ],
        "parameters": {
            "temperature": 0.8,
            "max_output_tokens": 100,
        },
    }

    resp1 = await async_client.post("/v1/chat", json=payload)
    assert resp1.status_code == 200
    assert resp1.json()["cached"] is False

    resp2 = await async_client.post("/v1/chat", json=payload)
    assert resp2.status_code == 200
    assert resp2.json()["cached"] is False
