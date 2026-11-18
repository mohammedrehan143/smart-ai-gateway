"""Unit tests for API contract schemas."""

import pytest
from pydantic import ValidationError
from app.api.schemas import (
    ChatCompletionRequest,
    ChatMessageSchema,
    ParametersSchema,
    RoutingSchema,
)


def test_valid_request_schema():
    req = ChatCompletionRequest(
        messages=[ChatMessageSchema(role="user", content="Hello gateway")],
        routing=RoutingSchema(policy="adaptive"),
        parameters=ParametersSchema(temperature=0.7, max_output_tokens=500),
    )
    assert len(req.messages) == 1
    assert req.messages[0].content == "Hello gateway"
    assert req.routing.policy == "adaptive"
    assert req.parameters.temperature == 0.7


def test_empty_messages_validation():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(messages=[])


def test_invalid_temperature_bounds():
    with pytest.raises(ValidationError):
        ParametersSchema(temperature=3.5)
    with pytest.raises(ValidationError):
        ParametersSchema(temperature=-0.5)


def test_invalid_policy():
    with pytest.raises(ValidationError):
        RoutingSchema(policy="invalid_policy")  # type: ignore


def test_empty_content_in_chat_message_schema():
    """Verify assistant messages and tool call messages can have empty/optional content."""
    msg = ChatMessageSchema(role="assistant", content="")
    assert msg.content == ""
    assert msg.role == "assistant"

    msg_none = ChatMessageSchema(role="assistant")
    assert msg_none.content == ""

    msg_tools = ChatMessageSchema(
        role="assistant",
        content="",
        tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": "{}"}}],
    )
    assert msg_tools.tool_calls is not None
    assert len(msg_tools.tool_calls) == 1
