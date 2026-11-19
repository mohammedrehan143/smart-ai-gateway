"""Pydantic V2 schemas for Smart AI CLI data validation."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class GatewayConfig(BaseModel):
    gateway_url: str = Field(default="https://smart-ai-gateway.onrender.com")
    default_policy: Literal["adaptive", "always_cheap", "always_strong"] = Field(default="adaptive")
    default_mode: str = Field(default="auto", description="Default mode: auto, fast, balanced, strong, expert")
    default_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    timeout_seconds: float = Field(default=30.0, gt=0.0)
    stream_output: bool = Field(default=True)


class PricingInfo(BaseModel):
    input_rate_per_million: float = 0.0
    output_rate_per_million: float = 0.0
    currency: str = "USD"
    rate_card_version: str = "default"


class ModelInfo(BaseModel):
    id: str
    alias: str
    provider: str
    upstream_model_id: str
    tier: Literal["cheap", "strong"]
    context_window: int
    max_output_tokens: int
    supports_tools: bool = True
    supports_json: bool = True
    is_active: bool = True
    version: str = "1.0.0"
    pricing: PricingInfo = Field(default_factory=PricingInfo)


class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo] = Field(default_factory=list)
    total: int = 0


class UsageAnalyticsResponse(BaseModel):
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    avg_latency_ms: float = 0.0
    cache_hits: int = 0
    cache_hit_rate: float = 0.0
    fallback_count: int = 0
    policy_breakdown: Dict[str, int] = Field(default_factory=dict)
    model_breakdown: Dict[str, int] = Field(default_factory=dict)
    recent_requests: List[Dict[str, Any]] = Field(default_factory=list)


class ModelCostSummary(BaseModel):
    spend: float = 0.0
    tokens: int = 0
    requests: int = 0


class ProviderCostSummary(BaseModel):
    spend: float = 0.0
    requests: int = 0


class CostAnalyticsResponse(BaseModel):
    total_spend: float = 0.0
    calculated_spend: float = 0.0
    estimated_spend: float = 0.0
    currency: str = "USD"
    model_breakdown: Dict[str, ModelCostSummary] = Field(default_factory=dict)
    provider_breakdown: Dict[str, ProviderCostSummary] = Field(default_factory=dict)


class RoutingDecisionRecord(BaseModel):
    decision_id: Optional[str] = None
    trace_id: str
    policy: str
    policy_version: Optional[str] = "1.0.0"
    selected_provider: str
    selected_model: str
    tier: Literal["cheap", "strong"]
    reason_code: Optional[str] = None
    reason: str
    features: Dict[str, Any] = Field(default_factory=dict)
    complexity: Optional[str] = None
    strategy: Optional[str] = None
    alternative_eligible_models: Optional[List[str]] = None
    fallback_reason: Optional[str] = None
    latency_ms: int = 0
    total_tokens: int = 0
    cost_estimate: Optional[float] = None
    fallback_used: bool = False
    created_at: Optional[float] = None


class RoutingDecisionsResponse(BaseModel):
    decisions: List[RoutingDecisionRecord] = Field(default_factory=list)
    count: int = 0


class BenchmarkSummaryItem(BaseModel):
    policy: str
    total_cases: int
    passed_cases: int
    pass_rate_pct: float
    avg_score: float
    total_cost: float
    avg_cost_per_task: float
    avg_latency_ms: float
    fallback_count: int
    category_scores: Dict[str, float] = Field(default_factory=dict)


class BenchmarkRunResponse(BaseModel):
    dataset_version: str
    cases_evaluated: int
    summaries: Dict[str, BenchmarkSummaryItem] = Field(default_factory=dict)
    adaptive_savings_vs_strong_pct: float = 0.0


class AuthVerifyResponse(BaseModel):
    status: str
    auth_enforced: bool
    gateway_version: str
    environment: str
    timestamp: str
    routing_policy_version: Optional[str] = None
    rate_card_version: Optional[str] = None
