"""Domain entities and value objects."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


def generate_id(prefix: str) -> str:
    """Generate prefixed identifier with timestamp component."""
    return f"{prefix}_{int(time.time() * 1000):x}_{uuid.uuid4().hex[:12]}"


@dataclass
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class RoutingOptions:
    policy: str = "adaptive"  # adaptive, always_cheap, always_strong, cost_optimized, balanced, quality_first, performance_optimized, manual
    preference: Optional[str] = "balanced"
    strategy: Optional[str] = None
    quality_threshold: Optional[float] = None
    manual_model: Optional[str] = None
    enable_collaboration: bool = False
    collaboration_strategy: Optional[str] = None
    enable_bandit: bool = True
    user_id: str = "default_user"
    project_id: str = "default_project"
    max_cost_limit: Optional[float] = None
    mode: Optional[str] = None  # auto, fast, balanced, strong, expert


@dataclass
class GenerationParameters:
    temperature: float = 0.2
    max_output_tokens: int = 1024


@dataclass
class RoutingDecision:
    policy_name: str
    policy_version: str
    tier: Literal["cheap", "strong"]
    selected_model_alias: str
    selected_provider: str
    reason_code: str
    reason_message: str
    feature_summary: Dict[str, Any] = field(default_factory=dict)
    fallback_used: bool = False
    complexity: str = "SIMPLE"  # SIMPLE, MODERATE, COMPLEX, EXPERT
    strategy: str = "balanced"
    task_category: str = "general_chat"
    alternative_eligible_models: List[str] = field(default_factory=list)
    estimated_cost: Optional[float] = None
    fallback_reason: Optional[str] = None
    candidate_progression: List[str] = field(default_factory=list)
    bandit_score: Optional[float] = None
    agentic_plan: Optional[Dict[str, Any]] = None
    evaluation: Optional[Dict[str, Any]] = None
    classification_level: int = 1
    agent: str = "Weak Agent"
    mock_mode: bool = False
    selected_mode: str = "auto"
    routing_reason: Optional[str] = None
    actual_provider: Optional[str] = None
    actual_model: Optional[str] = None
    reasoning_effort: str = "none"
    fallback_status: str = "not_triggered"
    token_usage: Optional[Dict[str, int]] = None
    latency_ms: Optional[int] = None


@dataclass
class NormalizedCompletion:
    content: str
    finish_reason: Literal["stop", "length", "tool_calls", "error"]
    provider: str
    model_alias: str
    provider_request_id: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    raw_usage_available: bool = True
    tool_calls: Optional[List[Dict[str, Any]]] = None
    is_mock: bool = False


@dataclass
class UsageRecord:
    id: str = field(default_factory=lambda: generate_id("usg"))
    gateway_request_id: str = ""
    provider_attempt_id: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    usage_source: Literal["provider", "estimated", "missing"] = "provider"
    rate_card_id: Optional[str] = None
    input_rate: Optional[float] = None
    output_rate: Optional[float] = None
    estimated_cost: Optional[float] = None
    currency: str = "USD"
    cost_status: Literal["calculated", "estimated", "unavailable"] = "unavailable"


@dataclass
class ProviderAttemptRecord:
    id: str = field(default_factory=lambda: generate_id("att"))
    gateway_request_id: str = ""
    attempt_number: int = 1
    provider: str = ""
    model_alias: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    latency_ms: int = 0
    status: Literal["success", "failure", "timeout"] = "success"
    error_category: Optional[str] = None
    http_status: Optional[int] = None
    retry_after_ms: Optional[int] = None
    is_fallback: bool = False
    provider_request_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayRequestRecord:
    id: str = field(default_factory=lambda: generate_id("req"))
    trace_id: str = field(default_factory=lambda: generate_id("tr"))
    request_id: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    environment: str = "local"
    gateway_version: str = "0.1.0"
    api_version: str = "v1"
    routing_policy: str = "adaptive"
    routing_policy_version: str = "1.0.0"
    status: Literal["success", "error"] = "success"
    error_category: Optional[str] = None
    cache_status: Literal["hit", "miss", "bypass"] = "miss"
    final_provider: Optional[str] = None
    final_model_alias: Optional[str] = None
    fallback_used: bool = False
    latency_ms: int = 0
    prompt_fingerprint: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
