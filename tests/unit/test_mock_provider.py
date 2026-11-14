"""Unit tests for MockProviderAdapter."""

import pytest
from app.core.errors import ProviderServerError, RateLimitError, RequestTimeoutError
from app.domain.entities import ChatMessage, GenerationParameters
from app.providers.mock import MockProviderAdapter


@pytest.mark.asyncio
async def test_mock_provider_success():
    adapter = MockProviderAdapter()
    messages = [ChatMessage(role="user", content="Calculate total sum")]
    params = GenerationParameters()

    completion = await adapter.generate(
        messages=messages,
        parameters=params,
        model_alias="mock-cheap",
        timeout_seconds=5.0,
    )

    assert completion.finish_reason == "stop"
    assert "Mock completion response" in completion.content
    assert completion.input_tokens > 0
    assert completion.output_tokens > 0
    assert completion.raw_usage_available is True


@pytest.mark.asyncio
async def test_mock_provider_failures():
    timeout_adapter = MockProviderAdapter(failure_mode="timeout")
    with pytest.raises(RequestTimeoutError):
        await timeout_adapter.generate(
            messages=[ChatMessage(role="user", content="hi")],
            parameters=GenerationParameters(),
            model_alias="mock-cheap",
            timeout_seconds=1.0,
        )

    server_error_adapter = MockProviderAdapter(failure_mode="500")
    with pytest.raises(ProviderServerError):
        await server_error_adapter.generate(
            messages=[ChatMessage(role="user", content="hi")],
            parameters=GenerationParameters(),
            model_alias="mock-cheap",
            timeout_seconds=1.0,
        )

    rate_limit_adapter = MockProviderAdapter(failure_mode="429")
    with pytest.raises(RateLimitError):
        await rate_limit_adapter.generate(
            messages=[ChatMessage(role="user", content="hi")],
            parameters=GenerationParameters(),
            model_alias="mock-cheap",
            timeout_seconds=1.0,
        )
