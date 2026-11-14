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
