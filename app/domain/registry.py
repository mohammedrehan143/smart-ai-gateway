"""Capability-aware model registry with quality tiers and pricing specifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Set


@dataclass
class ModelMetadata:
    alias: str
    provider: str
    upstream_model_id: str
    tier: Literal["cheap", "strong"]
    context_window: int
    max_output_tokens: int
    quality_tier: int = 1  # 1: Basic/Simple, 2: Moderate/Capable, 3: Complex/Advanced, 4: Expert/Frontier
    quality_score: float = 0.70  # Normalized quality score (0.0 - 1.0)
    latency_tier: Literal["fast", "standard", "slow"] = "fast"
    supports_tools: bool = True
    supports_json: bool = True
    capabilities: List[str] = field(default_factory=lambda: ["chat", "general_knowledge"])
    input_rate_per_million: float = 0.15
    output_rate_per_million: float = 0.60
    reliability_score: float = 0.99
    is_active: bool = True
    version: str = "1.0.0"

    def satisfies_capabilities(self, required_capabilities: Set[str]) -> bool:
        """Verifies if model supports all required task capabilities."""
        if not required_capabilities:
            return True
        model_caps = set(self.capabilities)
        if self.supports_tools:
            model_caps.add("tools")
        if self.supports_json:
            model_caps.add("json")
        return required_capabilities.issubset(model_caps)


class ModelRegistry:
    """Registry of allowlisted models, capabilities, and operational parameters."""

    def __init__(self):
        self._models: Dict[str, ModelMetadata] = {
            "mock-cheap": ModelMetadata(
                alias="mock-cheap",
                provider="mock",
                upstream_model_id="mock-cheap-v1",
                tier="cheap",
                context_window=16384,
                max_output_tokens=4096,
                quality_tier=2,
                quality_score=0.75,
                latency_tier="fast",
                supports_tools=True,
                supports_json=True,
                capabilities=["chat", "general_knowledge", "qa", "summarization", "code_simple", "structured_writing"],
                input_rate_per_million=0.15,
                output_rate_per_million=0.60,
                reliability_score=0.995,
                is_active=True,
            ),
            "mock-strong": ModelMetadata(
                alias="mock-strong",
                provider="mock",
                upstream_model_id="mock-strong-v1",
                tier="strong",
                context_window=128000,
                max_output_tokens=8192,
                quality_tier=4,
                quality_score=0.98,
                latency_tier="standard",
                supports_tools=True,
                supports_json=True,
                capabilities=[
                    "chat",
                    "general_knowledge",
                    "qa",
                    "summarization",
                    "code_simple",
                    "code_complex",
                    "debugging",
                    "architecture",
                    "deep_reasoning",
                    "security_analysis",
                    "structured_writing",
                ],
                input_rate_per_million=2.50,
                output_rate_per_million=10.00,
                reliability_score=0.990,
                is_active=True,
            ),
            "gpt-4o-mini": ModelMetadata(
                alias="gpt-4o-mini",
                provider="openai",
                upstream_model_id="gpt-4o-mini",
                tier="cheap",
                context_window=128000,
                max_output_tokens=16384,
                quality_tier=2,
                quality_score=0.82,
                latency_tier="fast",
                supports_tools=True,
                supports_json=True,
                capabilities=["chat", "general_knowledge", "qa", "summarization", "code_simple", "structured_writing"],
                input_rate_per_million=0.15,
                output_rate_per_million=0.60,
                reliability_score=0.999,
                is_active=True,
            ),
            "gpt-4o": ModelMetadata(
                alias="gpt-4o",
                provider="openai",
                upstream_model_id="gpt-4o",
                tier="strong",
                context_window=128000,
                max_output_tokens=16384,
                quality_tier=4,
                quality_score=0.98,
                latency_tier="standard",
                supports_tools=True,
                supports_json=True,
                capabilities=[
                    "chat",
                    "general_knowledge",
                    "qa",
                    "summarization",
                    "code_simple",
                    "code_complex",
                    "debugging",
                    "architecture",
                    "deep_reasoning",
                    "security_analysis",
                    "structured_writing",
                    "multimodal",
                ],
                input_rate_per_million=2.50,
                output_rate_per_million=10.00,
                reliability_score=0.995,
                is_active=True,
            ),
        }

    def get_model(self, alias: str) -> Optional[ModelMetadata]:
        return self._models.get(alias)

    def register(self, model: ModelMetadata) -> None:
        self._models[model.alias] = model

    def list_models(self) -> List[ModelMetadata]:
        return list(self._models.values())

    def get_by_tier(self, tier: Literal["cheap", "strong"], provider: Optional[str] = None) -> List[ModelMetadata]:
        return [
            m
            for m in self._models.values()
            if m.tier == tier and (provider is None or m.provider == provider) and m.is_active
        ]

    def filter_eligible_models(
        self,
        min_quality_score: float = 0.0,
        required_capabilities: Optional[Set[str]] = None,
        max_prompt_tokens: int = 0,
        provider: Optional[str] = None,
    ) -> List[ModelMetadata]:
        """Finds all active models that satisfy task requirements."""
        req_caps = required_capabilities or set()
        eligible: List[ModelMetadata] = []

        for m in self._models.values():
            if not m.is_active:
                continue
            if provider and m.provider != provider:
                continue
            if max_prompt_tokens > 0 and max_prompt_tokens > m.context_window:
                continue
            if m.quality_score < min_quality_score:
                continue
            if not m.satisfies_capabilities(req_caps):
                continue
            eligible.append(m)

        return eligible


registry = ModelRegistry()
