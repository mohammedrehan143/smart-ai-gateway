"""Unit tests for cache key generation and in-memory TTL caching."""

import asyncio
import pytest
from app.domain.cache import compute_cache_key, is_cache_eligible
from app.domain.entities import ChatMessage, GenerationParameters, NormalizedCompletion
from app.services.cache_service import InMemoryCacheService


def test_cache_key_generation():
    messages = [ChatMessage(role="user", content="Test prompt")]
    params = GenerationParameters(temperature=0.0, max_output_tokens=500)
    k1 = compute_cache_key("mock-cheap", messages, params)
    k2 = compute_cache_key("mock-cheap", messages, params)
    assert k1 == k2
    assert len(k1) == 64

    # Changing temperature changes key
    params_diff = GenerationParameters(temperature=0.5, max_output_tokens=500)
    k3 = compute_cache_key("mock-cheap", messages, params_diff)
    assert k1 != k3


def test_cache_eligibility():
    assert is_cache_eligible(GenerationParameters(temperature=0.0)) is True
    assert is_cache_eligible(GenerationParameters(temperature=0.7)) is False
    assert is_cache_eligible(GenerationParameters(temperature=0.7), force_cache=True) is True


@pytest.mark.asyncio
async def test_in_memory_cache_ttl():
    cache = InMemoryCacheService(default_ttl_seconds=1)
    completion = NormalizedCompletion(
        content="Cached text",
        finish_reason="stop",
        provider="mock",
        model_alias="mock-cheap",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
    )

    await cache.set("test-key", completion, ttl_seconds=1)
    cached = await cache.get("test-key")
    assert cached is not None
    assert cached.content == "Cached text"
    assert cache.hits == 1

    # Wait for TTL to expire
    await asyncio.sleep(1.1)
    expired = await cache.get("test-key")
    assert expired is None
    assert cache.misses == 1
