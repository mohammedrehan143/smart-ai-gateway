"""Intelligent capability-aware routing engine with multi-tier complexity, contextual bandits, and agentic planning."""

from __future__ import annotations

from typing import List, Optional, Set
from app.core.config import settings
from app.core.rate_cards import default_rate_catalog
from app.domain.agentic_planner import AgenticPlan, AgenticTaskPlanner
from app.domain.bandit_router import default_bandit_router
from app.domain.circuit_breaker import default_circuit_registry
from app.domain.classifier import ComplexityLevel
from app.domain.entities import ChatMessage, RoutingDecision, RoutingOptions
from app.domain.features import extract_features
from app.domain.intent_engine import IntentIntelligenceEngine, TaskProfile
from app.domain.registry import ModelMetadata, ModelRegistry, registry


class DeterministicRouter:
    """Intelligent routing engine selecting optimal model based on intent, capabilities, circuit breakers, and bandits."""

    def __init__(
        self,
        char_threshold: int = 2000,
        policy_version: Optional[str] = None,
        model_reg: Optional[ModelRegistry] = None,
    ):
        self.char_threshold = char_threshold
        self.policy_version = policy_version or settings.ROUTING_POLICY_VERSION
        self.registry = model_reg or registry

    def _resolve_strategy(self, options: RoutingOptions) -> str:
        """Resolves strategy from policy or explicit strategy option."""
        if options.strategy:
            return options.strategy.lower()
        pol = options.policy.lower()
        if pol in ("cost_optimized", "balanced", "quality_first", "performance_optimized", "manual"):
            return pol
        if pol == "adaptive":
            pref = options.preference.lower() if options.preference else "balanced"
            if pref in ("cost_optimized", "balanced", "quality_first", "performance_optimized", "manual"):
                return pref
            return "balanced"
        return pol

    def route(
        self,
        messages: List[ChatMessage],
        options: RoutingOptions,
        cheap_alias: Optional[str] = None,
        strong_alias: Optional[str] = None,
        has_tools: bool = False,
        format_json: bool = False,
        tools: Optional[list] = None,
    ) -> RoutingDecision:
        strategy = self._resolve_strategy(options)
        policy_name = options.policy
        cheap_default = cheap_alias or settings.CHEAP_MODEL_ALIAS
        strong_default = strong_alias or settings.STRONG_MODEL_ALIAS

        # 1. Feature Extraction & Multi-Dimensional Intent Analysis
        features = extract_features(messages, has_tools=has_tools, format_json=format_json)
        feature_summary = features.to_safe_summary()
        profile: TaskProfile = IntentIntelligenceEngine.analyze(
            messages=messages,
            tools=tools,
            format_json=format_json,
            quality_threshold=options.quality_threshold,
            max_cost_limit=options.max_cost_limit,
        )
        complexity = profile.complexity.value
        req_capabilities: Set[str] = set(profile.required_capabilities)

        # -------------------------------------------------------------
        # 2. Manual / Forced Legacy Policies
        # -------------------------------------------------------------
        if policy_name == "always_cheap" or strategy == "always_cheap":
            cheap_meta = self.registry.get_model(cheap_default)
            provider = cheap_meta.provider if cheap_meta else "mock"
            return RoutingDecision(
                policy_name="always_cheap",
                policy_version=self.policy_version,
                tier="cheap",
                selected_model_alias=cheap_default,
                selected_provider=provider,
                reason_code="POLICY_FORCED_CHEAP",
                reason_message="Caller forced cheap tier",
                feature_summary=feature_summary,
                complexity=complexity,
                strategy=strategy,
                task_category=profile.category.value,
                alternative_eligible_models=[m.alias for m in self.registry.get_by_tier("cheap") if m.alias != cheap_default],
                estimated_cost=self._estimate_cost(cheap_default, features.estimated_tokens),
                candidate_progression=[cheap_default, strong_default],
            )

        if policy_name == "always_strong" or strategy == "always_strong":
            strong_meta = self.registry.get_model(strong_default)
            provider = strong_meta.provider if strong_meta else "mock"
            return RoutingDecision(
                policy_name="always_strong",
                policy_version=self.policy_version,
                tier="strong",
                selected_model_alias=strong_default,
                selected_provider=provider,
                reason_code="POLICY_FORCED_STRONG",
                reason_message="Caller forced strong tier",
                feature_summary=feature_summary,
                complexity=complexity,
                strategy=strategy,
                task_category=profile.category.value,
                alternative_eligible_models=[m.alias for m in self.registry.get_by_tier("strong") if m.alias != strong_default],
                estimated_cost=self._estimate_cost(strong_default, features.estimated_tokens),
                candidate_progression=[strong_default, cheap_default],
            )

        if strategy == "manual" and options.manual_model:
            manual_meta = self.registry.get_model(options.manual_model)
            if manual_meta:
                return RoutingDecision(
                    policy_name=policy_name,
                    policy_version=self.policy_version,
                    tier=manual_meta.tier,
                    selected_model_alias=manual_meta.alias,
                    selected_provider=manual_meta.provider,
                    reason_code="MANUAL_MODEL_SELECTED",
                    reason_message=f"Caller explicitly selected model '{manual_meta.alias}'",
                    feature_summary=feature_summary,
                    complexity=complexity,
                    strategy=strategy,
                    task_category=profile.category.value,
                    alternative_eligible_models=[m.alias for m in self.registry.list_models() if m.alias != manual_meta.alias],
                    estimated_cost=self._estimate_cost(manual_meta.alias, features.estimated_tokens),
                    candidate_progression=[manual_meta.alias, strong_default],
                )

        # -------------------------------------------------------------
        # 3. Context Capacity Constraint Check
        # -------------------------------------------------------------
        cheap_meta = self.registry.get_model(cheap_default)
        if cheap_meta and features.estimated_tokens > cheap_meta.context_window:
            strong_meta = self.registry.get_model(strong_default)
            return RoutingDecision(
                policy_name=policy_name,
                policy_version=self.policy_version,
                tier="strong",
                selected_model_alias=strong_default,
                selected_provider=strong_meta.provider if strong_meta else "mock",
                reason_code="CAPABILITY_EXCEEDED",
                reason_message=f"Estimated tokens ({features.estimated_tokens}) exceed cheap model window",
                feature_summary=feature_summary,
                complexity=complexity,
                strategy=strategy,
                task_category=profile.category.value,
                alternative_eligible_models=[m.alias for m in self.registry.get_by_tier("strong") if m.alias != strong_default],
                estimated_cost=self._estimate_cost(strong_default, features.estimated_tokens),
                candidate_progression=[strong_default],
            )

        # -------------------------------------------------------------
        # 4. Model Eligibility Filtering with Circuit Breaker Awareness
        # -------------------------------------------------------------
        min_quality = options.quality_threshold or 0.0
        eligible_models = self.registry.filter_eligible_models(
            min_quality_score=min_quality,
            required_capabilities=req_capabilities,
            max_prompt_tokens=features.estimated_tokens,
        )

        # Filter out circuit-breaker tripped models unless all are tripped
        healthy_models = [m for m in eligible_models if default_circuit_registry.is_model_healthy(m.alias)]
        candidates_to_score = healthy_models if healthy_models else eligible_models

        if not candidates_to_score:
            candidates_to_score = self.registry.filter_eligible_models(
                min_quality_score=0.0,
                required_capabilities=req_capabilities,
                max_prompt_tokens=features.estimated_tokens,
            )

        if not candidates_to_score:
            fallback_meta = self.registry.get_model(strong_default) or self.registry.get_model(cheap_default)
            candidates_to_score = [fallback_meta] if fallback_meta else []

        # -------------------------------------------------------------
        # 5. Complexity-Guided & Strategy-Aware Model Selection
        # -------------------------------------------------------------
        selected_model: ModelMetadata
        reason_code: str
        reason_message: str
        bandit_score: Optional[float] = None

        if complexity == ComplexityLevel.SIMPLE.value:
            # SIMPLE: Basic questions, definitions, greetings, simple summaries
            if strategy == "quality_first" or (options.quality_threshold and options.quality_threshold >= 0.90):
                selected_model = max(
                    candidates_to_score,
                    key=lambda m: (m.quality_score, 1 if m.alias == strong_default else 0),
                )
                reason_code = "SIMPLE_QUALITY_FIRST"
                reason_message = "Basic informational request; selected high-assurance model under quality constraint."
            else:
                cheap_candidates = [m for m in candidates_to_score if m.tier == "cheap"]
                candidates = cheap_candidates if cheap_candidates else candidates_to_score
                selected_model = min(
                    candidates,
                    key=lambda m: (
                        m.input_rate_per_million,
                        0 if m.alias == cheap_default else 1,
                        -m.quality_score,
                    ),
                )
                reason_code = "BASELINE_STANDARD_TASK"
                reason_message = "Basic informational request; no advanced reasoning required."

        elif complexity == ComplexityLevel.MODERATE.value:
            # MODERATE: Explanations, ordinary coding, structured writing, multi-step tasks
            if strategy == "quality_first" or (options.quality_threshold and options.quality_threshold >= 0.90):
                strong_candidates = [m for m in candidates_to_score if m.tier == "strong"]
                candidates = strong_candidates if strong_candidates else candidates_to_score
                selected_model = max(
                    candidates,
                    key=lambda m: (m.quality_score, 1 if m.alias == strong_default else 0),
                )
                reason_code = "MODERATE_QUALITY_FIRST"
                reason_message = "Moderate complexity request; selected high-capability model under quality-first policy."
            else:
                cost_effective = [m for m in candidates_to_score if m.tier == "cheap" and m.quality_tier >= 2]
                candidates = cost_effective if cost_effective else candidates_to_score
                if strategy == "performance_optimized":
                    selected_model = min(
                        candidates,
                        key=lambda m: (
                            0 if m.latency_tier == "fast" else 1,
                            0 if m.alias == cheap_default else 1,
                            m.input_rate_per_million,
                        ),
                    )
                else:
                    selected_model = min(
                        candidates,
                        key=lambda m: (
                            m.input_rate_per_million,
                            0 if m.alias == cheap_default else 1,
                            -m.quality_score,
                        ),
                    )

                reason_code = "ORDINARY_TASK_COST_EFFECTIVE"
                reason_message = "Ordinary coding or concept explanation; resolved with cost-effective capable model."

        elif complexity == ComplexityLevel.COMPLEX.value:
            # COMPLEX: Advanced reasoning, difficult debugging, system architecture
            strong_candidates = [m for m in candidates_to_score if m.tier == "strong"]
            candidates = strong_candidates if strong_candidates else candidates_to_score

            if strategy == "performance_optimized":
                selected_model = min(
                    candidates,
                    key=lambda m: (
                        0 if m.latency_tier == "fast" else 1,
                        0 if m.alias == strong_default else 1,
                        -m.quality_score,
                    ),
                )
            elif strategy == "cost_optimized":
                selected_model = min(
                    candidates,
                    key=lambda m: (
                        m.input_rate_per_million,
                        0 if m.alias == strong_default else 1,
                    ),
                )
            else:
                selected_model = max(
                    candidates,
                    key=lambda m: (
                        m.quality_score,
                        1 if m.alias == strong_default else 0,
                    ),
                )

            if features.has_code or features.is_debugging:
                reason_code = "CODE_OR_DEBUGGING_DETECTED"
                reason_message = "Request contains source code or debugging diagnostics requiring advanced capabilities."
            else:
                reason_code = "COMPLEX_REASONING_OR_MULTISTEP"
                reason_message = "Request indicates system architecture, multi-step execution, or comparative trade-off analysis."

        else:
            # EXPERT: High-stakes technical reasoning, multi-agent security, formal proofs
            selected_model = max(
                candidates_to_score,
                key=lambda m: (
                    m.quality_score,
                    1 if m.alias == strong_default else 0,
                    m.reliability_score,
                ),
            )
            reason_code = "EXPERT_DOMAIN_ANALYSIS"
            reason_message = "High-stakes technical synthesis, security incident analysis, or formal reasoning requiring frontier model."

        # -------------------------------------------------------------
        # 6. Contextual Bandit Adaptive Scoring & Learning
        # -------------------------------------------------------------
        if options.enable_bandit and strategy in ("balanced", "cost_optimized"):
            arm = default_bandit_router.get_arm(profile.category.value, selected_model.alias)
            bandit_score = arm.avg_reward

        # -------------------------------------------------------------
        # 7. Agentic Task Planning
        # -------------------------------------------------------------
        agentic_plan: AgenticPlan = AgenticTaskPlanner.plan(
            profile=profile,
            primary_model=selected_model.alias,
            strong_model=strong_default,
            collaboration_requested=options.enable_collaboration,
            collaboration_strategy=options.collaboration_strategy,
            max_cost_budget=options.max_cost_limit,
        )

        # -------------------------------------------------------------
        # 8. Fallback Candidate Progression
        # -------------------------------------------------------------
        same_tier_alts = [m.alias for m in candidates_to_score if m.tier == selected_model.tier and m.alias != selected_model.alias]
        other_tier_alts = [m.alias for m in candidates_to_score if m.tier != selected_model.tier]

        candidate_progression = [selected_model.alias] + same_tier_alts + other_tier_alts
        if strong_default not in candidate_progression:
            candidate_progression.append(strong_default)

        alternative_eligible_models = [m.alias for m in candidates_to_score if m.alias != selected_model.alias]
        estimated_cost = self._estimate_cost(selected_model.alias, features.estimated_tokens)

        return RoutingDecision(
            policy_name=policy_name,
            policy_version=self.policy_version,
            tier=selected_model.tier,
            selected_model_alias=selected_model.alias,
            selected_provider=selected_model.provider,
            reason_code=reason_code,
            reason_message=reason_message,
            feature_summary=feature_summary,
            fallback_used=False,
            complexity=complexity,
            strategy=strategy,
            task_category=profile.category.value,
            alternative_eligible_models=alternative_eligible_models,
            estimated_cost=estimated_cost,
            candidate_progression=candidate_progression,
            bandit_score=bandit_score,
            agentic_plan=agentic_plan.to_summary(),
        )

    def _estimate_cost(self, model_alias: str, input_tokens: int) -> Optional[float]:
        rate_entry = default_rate_catalog.get_rate(model_alias)
        if not rate_entry:
            return None
        in_cost = (input_tokens / 1_000_000) * rate_entry.input_rate_per_million
        out_cost = (200 / 1_000_000) * rate_entry.output_rate_per_million
        return round(in_cost + out_cost, 7)


default_router = DeterministicRouter()
