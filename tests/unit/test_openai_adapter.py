"""Unit tests for OpenAICompatibleAdapter using MockTransport."""

import httpx
import pytest
from app.core.errors import ProviderAuthError, ProviderServerError, RateLimitError
from app.domain.entities import ChatMessage, GenerationParameters
from app.providers.openai_compatible import OpenAICompatibleAdapter


@pytest.mark.asyncio
async def test_openai_adapter_success():
    mock_payload = {
        "id": "chatcmpl_mock_123",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from mock OpenAI!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 8,
            "total_tokens": 23,
        },
    }

    def handler(request: httpx.Request):
        assert "Authorization" in request.headers
        assert request.headers["Authorization"] == "Bearer mock-key"
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    adapter = OpenAICompatibleAdapter(api_key="mock-key", http_client=client)
    completion = await adapter.generate(
        messages=[ChatMessage(role="user", content="Hi")],
        parameters=GenerationParameters(),
        model_alias="gpt-4o-mini",
        timeout_seconds=5.0,
    )

    assert completion.content == "Hello from mock OpenAI!"
    assert completion.input_tokens == 15
    assert completion.output_tokens == 8
    assert completion.total_tokens == 23
    assert completion.raw_usage_available is True


@pytest.mark.asyncio
async def test_openai_adapter_errors():
    # 401 Unauthorized
    client_401 = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(401)))
    adapter_401 = OpenAICompatibleAdapter(api_key="bad-key", http_client=client_401)
    with pytest.raises(ProviderAuthError):
        await adapter_401.generate([ChatMessage(role="user", content="Hi")], GenerationParameters(), "gpt-4o-mini", 5.0)

    # 429 Rate Limit with Retry-After
    client_429 = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(429, headers={"Retry-After": "2"}))
    )
    adapter_429 = OpenAICompatibleAdapter(api_key="mock-key", http_client=client_429)
    with pytest.raises(RateLimitError) as exc_info:
        await adapter_429.generate([ChatMessage(role="user", content="Hi")], GenerationParameters(), "gpt-4o-mini", 5.0)
    assert exc_info.value.retry_after_s == 2.0

    # 500 Server Error
    client_500 = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(500)))
    adapter_500 = OpenAICompatibleAdapter(api_key="mock-key", http_client=client_500)
    with pytest.raises(ProviderServerError):
        await adapter_500.generate([ChatMessage(role="user", content="Hi")], GenerationParameters(), "gpt-4o-mini", 5.0)
