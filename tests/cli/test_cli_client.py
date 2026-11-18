"""Unit tests for GatewayClient HTTP communications and error mappings."""

import pytest
import httpx
from smart_ai_cli.client import (
    AuthenticationError,
    GatewayClient,
    GatewayClientError,
    GatewayServerError,
    RateLimitError,
)


def test_client_headers_generation():
    client = GatewayClient(base_url="http://localhost:8000", api_key="test-key-123")
    headers = client._headers({"X-Custom": "val"})
    assert headers["Authorization"] == "Bearer test-key-123"
    assert headers["Accept"] == "application/json"
    assert headers["X-Custom"] == "val"
    assert headers["X-Request-ID"].startswith("cli_")


def test_client_error_classification():
    client = GatewayClient(base_url="http://localhost:8000")

    # 401 Unauthorized
    resp_401 = httpx.Response(401, json={"error": {"message": "Invalid token"}})
    with pytest.raises(AuthenticationError, match="Invalid token"):
        client._handle_response_error(resp_401)

    # 429 Rate Limit
    resp_429 = httpx.Response(429, json={"error": {"message": "Too many requests"}})
    with pytest.raises(RateLimitError, match="Too many requests"):
        client._handle_response_error(resp_429)

    # 502 Bad Gateway
    resp_502 = httpx.Response(502, json={"error": {"message": "Upstream error"}})
    with pytest.raises(GatewayServerError, match="Upstream error"):
        client._handle_response_error(resp_502)

    # Generic 400
    resp_400 = httpx.Response(400, json={"error": {"message": "Bad request format"}})
    with pytest.raises(GatewayClientError, match="Bad request format"):
        client._handle_response_error(resp_400)


def test_client_sanitize_messages():
    """Verify empty text-only messages are stripped before sending to prevent 422 errors."""
    client = GatewayClient(base_url="http://localhost:8000")

    # Mixture of valid and empty messages
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": ""},
        {"role": "assistant", "content": "   "},
        {"role": "assistant", "content": None},
        {"role": "user", "content": "hy"},
    ]
    sanitized = client._sanitize_messages(messages)
    assert len(sanitized) == 2
    assert sanitized[0] == {"role": "user", "content": "Hello"}
    assert sanitized[1] == {"role": "user", "content": "hy"}

    # Assistant messages with tool calls should be preserved even if content is empty
    tool_msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "run"}}],
    }
    sanitized_tools = client._sanitize_messages([tool_msg])
    assert len(sanitized_tools) == 1
    assert sanitized_tools[0]["tool_calls"] is not None

