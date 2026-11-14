"""Pydantic V2 schemas matching docs/05_API_CONTRACT.md."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ChatMessageSchema(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(..., min_length=1)
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


class RoutingSchema(BaseModel):
    policy: Literal["adaptive", "always_cheap", "always_strong"] = "adaptive"
    preference: Optional[str] = "balanced"


class ParametersSchema(BaseModel):
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1024, gt=0, le=8192)


class ChatCompletionRequest(BaseModel):
    messages: List[ChatMessageSchema] = Field(..., min_length=1)
    routing: RoutingSchema = Field(default_factory=RoutingSchema)
    parameters: ParametersSchema = Field(default_factory=ParametersSchema)
    metadata: Optional[Dict[str, Any]] = None
    stream: bool = False



class ChoiceMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ChatChoice(BaseModel):
    index: int = 0
    message: ChoiceMessage
    finish_reason: Literal["stop", "length", "tool_calls", "error"] = "stop"


class UsageSchema(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_estimate: Optional[float] = None
    currency: str = "USD"
    cost_status: Literal["calculated", "estimated", "unavailable"] = "unavailable"


class RoutingDecisionSchema(BaseModel):
    policy: str
    policy_version: str
    tier: Literal["cheap", "strong"]
    reason: str
    fallback_used: bool = False


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["gateway.completion"] = "gateway.completion"
    created: int
    model: str
    provider: str
    choices: List[ChatChoice]
    usage: UsageSchema
    routing: RoutingDecisionSchema
    latency_ms: int
    trace_id: str
    cached: bool = False


class ErrorDetail(BaseModel):
    type: str
    message: str
    retryable: bool = False
    trace_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["live", "ready", "degraded", "down"]
    timestamp: str
    gateway_version: str
    database: Optional[str] = None
    environment: str
