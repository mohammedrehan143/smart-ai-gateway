"""Pydantic V2 schemas matching docs/05_API_CONTRACT.md with advanced agentic extensions."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ChatMessageSchema(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[str] = Field(default="")
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


class RoutingSchema(BaseModel):
    policy: Literal[
        "adaptive",
        "always_cheap",
        "always_strong",
        "cost_optimized",
        "balanced",
        "quality_first",
        "performance_optimized",
        "manual",
    ] = "adaptive"
    preference: Optional[str] = "balanced"
    strategy: Optional[Literal["cost_optimized", "balanced", "quality_first", "performance_optimized", "manual"]] = None
    quality_threshold: Optional[float] = None
    manual_model: Optional[str] = None
    enable_collaboration: bool = False
    collaboration_strategy: Optional[Literal["peer_review", "code_verification", "consensus"]] = None
    enable_bandit: bool = True
    user_id: Optional[str] = "default_user"
    project_id: Optional[str] = "default_project"
    max_cost_limit: Optional[float] = None


class ParametersSchema(BaseModel):
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1024, gt=0, le=8192)


class ChatCompletionRequest(BaseModel):
    messages: List[ChatMessageSchema] = Field(..., min_length=1)
    routing: RoutingSchema = Field(default_factory=RoutingSchema)
    parameters: ParametersSchema = Field(default_factory=ParametersSchema)
    tools: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    stream: bool = False
    user: Optional[str] = None


class ChoiceMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = ""
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
    tier: str
    reason: str
    fallback_used: bool = False
    complexity: Optional[str] = None
    strategy: Optional[str] = None
    task_category: Optional[str] = None
    alternative_eligible_models: Optional[List[str]] = None
    estimated_cost: Optional[float] = None
    fallback_reason: Optional[str] = None
    bandit_score: Optional[float] = None
    agentic_plan: Optional[Dict[str, Any]] = None
    evaluation: Optional[Dict[str, Any]] = None
    classification_level: Optional[int] = 1
    agent: Optional[str] = "Weak Agent"
    mock_mode: Optional[bool] = False


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


class CredentialCreateRequest(BaseModel):
    provider: str = Field(..., description="Provider name: openai, anthropic, google, groq")
    api_key: str = Field(..., min_length=5, description="Provider API key")
    base_url: Optional[str] = Field(None, description="Optional custom base URL")


class BudgetSetRequest(BaseModel):
    project_id: str = Field(default="default_project")
    max_cost_per_request: Optional[float] = Field(None, ge=0.0)
    daily_budget: Optional[float] = Field(None, ge=0.0)
    monthly_budget: Optional[float] = Field(None, ge=0.0)


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
