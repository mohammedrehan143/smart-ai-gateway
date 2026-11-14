"""Deterministic routing engine selecting model tier and alias."""

from __future__ import annotations

from typing import List, Optional
from app.core.config import settings
from app.domain.entities import ChatMessage, RoutingDecision, RoutingOptions
from app.domain.features import extract_features
from app.domain.registry import ModelRegistry, registry


class DeterministicRouter:
    """Deterministic routing engine implementing rules from docs/06_ROUTING_POLICY.md."""

    def __init__(
        self,
        char_threshold: int = 500,
        policy_version: Optional[str] = None,
        model_reg: Optional[ModelRegistry] = None,
    ):
        self.char_threshold = char_threshold
        self.policy_version = policy_version or settings.ROUTING_POLICY_VERSION
        self.registry = model_reg or registry

    def route(
        self,
        messages: List[ChatMessage],
        options: RoutingOptions,
        cheap_alias: Optional[str] = None,
        strong_alias: Optional[str] = None,
    ) -> RoutingDecision:
        policy = options.policy
        cheap_model = cheap_alias or settings.CHEAP_MODEL_ALIAS
        strong_model = strong_alias or settings.STRONG_MODEL_ALIAS

        features = extract_features(messages)
        feature_summary = features.to_safe_summary()

        # Rule 1: Always Cheap policy
        if policy == "always_cheap":
            cheap_meta = self.registry.get_model(cheap_model)
            provider = cheap_meta.provider if cheap_meta else "mock"
            return RoutingDecision(
                policy_name="always_cheap",
                policy_version=self.policy_version,
                tier="cheap",
                selected_model_alias=cheap_model,
                selected_provider=provider,
                reason_code="POLICY_FORCED_CHEAP",
                reason_message="Caller forced cheap tier",
                feature_summary=feature_summary,
            )

        # Rule 2: Always Strong policy
        if policy == "always_strong":
            strong_meta = self.registry.get_model(strong_model)
            provider = strong_meta.provider if strong_meta else "mock"
            return RoutingDecision(
                policy_name="always_strong",
                policy_version=self.policy_version,
                tier="strong",
                selected_model_alias=strong_model,
                selected_provider=provider,
                reason_code="POLICY_FORCED_STRONG",
                reason_message="Caller forced strong tier",
                feature_summary=feature_summary,
            )

        # Rule 3: Adaptive Policy
        # Check context capacity
        cheap_meta = self.registry.get_model(cheap_model)
        strong_meta = self.registry.get_model(strong_model)

        if cheap_meta and features.estimated_tokens > cheap_meta.context_window:
            return RoutingDecision(
                policy_name="adaptive",
                policy_version=self.policy_version,
                tier="strong",
                selected_model_alias=strong_model,
                selected_provider=strong_meta.provider if strong_meta else "mock",
                reason_code="CAPABILITY_EXCEEDED",
                reason_message=f"Estimated tokens ({features.estimated_tokens}) exceed cheap model window",
                feature_summary=feature_summary,
            )

        # Code or debugging indicators
        if features.has_code or features.is_debugging:
            return RoutingDecision(
                policy_name="adaptive",
                policy_version=self.policy_version,
                tier="strong",
                selected_model_alias=strong_model,
                selected_provider=strong_meta.provider if strong_meta else "mock",
                reason_code="CODE_OR_DEBUGGING_DETECTED",
                reason_message="Request contains source code or debugging diagnostics",
                feature_summary=feature_summary,
            )

        # Multi-step tasks or complex reasoning
        if features.is_multistep or features.has_complex_reasoning:
            return RoutingDecision(
                policy_name="adaptive",
                policy_version=self.policy_version,
                tier="strong",
                selected_model_alias=strong_model,
                selected_provider=strong_meta.provider if strong_meta else "mock",
                reason_code="COMPLEX_REASONING_OR_MULTISTEP",
                reason_message="Request indicates multi-step execution or comparative trade-off analysis",
                feature_summary=feature_summary,
            )

        # Long prompt threshold
        if features.char_length > self.char_threshold:
            return RoutingDecision(
                policy_name="adaptive",
                policy_version=self.policy_version,
                tier="strong",
                selected_model_alias=strong_model,
                selected_provider=strong_meta.provider if strong_meta else "mock",
                reason_code="LONG_PROMPT_THRESHOLD",
                reason_message=f"Prompt length ({features.char_length} chars) exceeds threshold ({self.char_threshold})",
                feature_summary=feature_summary,
            )

        # Default standard baseline
        return RoutingDecision(
            policy_name="adaptive",
            policy_version=self.policy_version,
            tier="cheap",
            selected_model_alias=cheap_model,
            selected_provider=cheap_meta.provider if cheap_meta else "mock",
            reason_code="BASELINE_STANDARD_TASK",
            reason_message="Short standard routine request without code or multi-step indicators",
            feature_summary=feature_summary,
        )


default_router = DeterministicRouter()
