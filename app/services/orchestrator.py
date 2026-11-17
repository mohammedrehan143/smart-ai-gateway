"""Orchestrator coordinating intent analysis, budget checks, multi-model execution, evaluation, and telemetry."""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Optional
from app.api.schemas import (
    ChatChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChoiceMessage,
    RoutingDecisionSchema,
    UsageSchema,
)
from app.core.config import settings
from app.core.cost import default_cost_calculator
from app.core.errors import GatewayError, ProviderUnavailableError, RateLimitError
from app.core.logging import correlation_trace_id, get_logger
from app.core.metrics import default_metrics
from app.core.observability import default_tracer
from app.domain.agentic_planner import AgenticPlan, ExecutionStep
from app.domain.bandit_router import default_bandit_router
from app.domain.budget import default_budget_controller
from app.domain.cache import compute_cache_key, is_cache_eligible
from app.domain.collaboration import CollaborationExecutionEngine
from app.domain.entities import (
    ChatMessage,
    GatewayRequestRecord,
    GenerationParameters,
    NormalizedCompletion,
    ProviderAttemptRecord,
    RoutingDecision,
    RoutingOptions,
    UsageRecord,
    generate_id,
)
from app.domain.evaluator import InlineEvaluationResult, ResponseQualityEvaluator
from app.domain.interfaces import CacheService, TraceRepository
from app.domain.retry import DeadlineTracker, calculate_backoff, is_retryable_error
from app.domain.router import DeterministicRouter, default_router
from app.providers.base import BaseProviderAdapter
from app.providers.resolver import DynamicProviderAdapter
from app.repositories.sqlite import SqliteTraceRepository
from app.services.cache_service import default_cache_service
from app.services.semantic_cache import default_semantic_cache

logger = get_logger("orchestrator")


class ChatOrchestrator:
    """Core orchestration service coordinating request lifecycle from validation to provider response."""

    def __init__(
        self,
        repository: Optional[TraceRepository] = None,
        cache_service: Optional[CacheService] = None,
        default_adapter: Optional[BaseProviderAdapter] = None,
        router: Optional[DeterministicRouter] = None,
    ):
        self.repository = repository or SqliteTraceRepository(settings.DATABASE_URL)
        self.cache_service = cache_service or default_cache_service
        self.default_adapter = default_adapter or DynamicProviderAdapter()
        self.router = router or default_router
        self.cost_calculator = default_cost_calculator

    async def execute_chat(
        self,
        request: ChatCompletionRequest,
        client_request_id: Optional[str] = None,
        adapter_override: Optional[BaseProviderAdapter] = None,
    ) -> ChatCompletionResponse:
        start_time = time.time()
        req_id = generate_id("req")
        trace_id = correlation_trace_id.get(None) or generate_id("tr")
        request_id = client_request_id or request.metadata.get("request_id") if request.metadata else None

        span = default_tracer.start_span("orchestrator.execute_chat", trace_id=trace_id)
        user_id = request.routing.user_id or request.user or "default_user"
        project_id = request.routing.project_id or "default_project"

        # Domain message conversion
        domain_messages = [
            ChatMessage(
                role=m.role,
                content=m.content,
                name=m.name,
                tool_calls=m.tool_calls,
                tool_call_id=m.tool_call_id,
            )
            for m in request.messages
        ]
        params = GenerationParameters(
            temperature=request.parameters.temperature,
            max_output_tokens=request.parameters.max_output_tokens,
        )

        has_tools = bool(request.tools)
        format_json = False
        if request.parameters and getattr(request.parameters, "format_json", False):
            format_json = True

        # 1. Deterministic Auto-Routing & Intent Profiling
        routing_opts = RoutingOptions(
            policy=request.routing.policy,
            preference=request.routing.preference,
            strategy=request.routing.strategy,
            quality_threshold=request.routing.quality_threshold,
            manual_model=request.routing.manual_model,
            enable_collaboration=request.routing.enable_collaboration,
            collaboration_strategy=request.routing.collaboration_strategy,
            enable_bandit=request.routing.enable_bandit,
            user_id=user_id,
            project_id=project_id,
            max_cost_limit=request.routing.max_cost_limit,
        )
        routing_decision = self.router.route(
            messages=domain_messages,
            options=routing_opts,
            cheap_alias=settings.CHEAP_MODEL_ALIAS,
            strong_alias=settings.STRONG_MODEL_ALIAS,
            has_tools=has_tools,
            format_json=format_json,
            tools=request.tools,
        )

        model_alias = routing_decision.selected_model_alias
        tier = routing_decision.tier
        adapter = adapter_override or self.default_adapter
        provider_name = routing_decision.selected_provider

        # 2. Pre-Execution Budget & Financial Gatekeeping
        budget_ok, budget_err = default_budget_controller.check_budget_available(
            user_id=user_id,
            project_id=project_id,
            estimated_cost=routing_decision.estimated_cost or 0.0,
            request_cost_limit=request.routing.max_cost_limit,
        )
        if not budget_ok:
            span.finish(status="ERROR")
            raise RateLimitError(budget_err or "Budget exceeded", trace_id=trace_id)

        # 3. Two-Tier Caching (L1 Exact + L2 Context-Safe Semantic)
        prompt_fp = hashlib.sha256(" ".join(m.content for m in domain_messages).encode("utf-8")).hexdigest()[:16]
        force_cache = bool(request.metadata and request.metadata.get("enable_cache"))
        cache_eligible = is_cache_eligible(params, force_cache=force_cache)
        cache_key = compute_cache_key(model_alias, domain_messages, params) if cache_eligible else ""

        # Check L2 Semantic & Exact Cache
        cached_comp, cache_status = await default_semantic_cache.get(
            tenant_id=user_id,
            model_alias=model_alias,
            messages=domain_messages,
            parameters=params,
        )
        if not cached_comp and cache_eligible:
            cached_comp = await self.cache_service.get(cache_key)
            if cached_comp:
                cache_status = "hit_exact"

        if cached_comp:
            total_latency = int((time.time() - start_time) * 1000)
            cache_decision = RoutingDecision(
                policy_name=routing_decision.policy_name,
                policy_version=routing_decision.policy_version,
                tier=tier,
                selected_model_alias=model_alias,
                selected_provider=provider_name,
                reason_code="CACHE_HIT",
                reason_message="Served from cache" if "semantic" not in cache_status else "Served from semantic cache",
                feature_summary={"cache_key": cache_key, "cache_status": cache_status},
                fallback_used=False,
                complexity=routing_decision.complexity,
                strategy=routing_decision.strategy,
                task_category=routing_decision.task_category,
                alternative_eligible_models=routing_decision.alternative_eligible_models,
                estimated_cost=0.0,
                bandit_score=routing_decision.bandit_score,
                agentic_plan=routing_decision.agentic_plan,
            )

            cost_res = self.cost_calculator.calculate(
                model_alias=model_alias,
                input_tokens=cached_comp.input_tokens,
                output_tokens=cached_comp.output_tokens,
                is_provider_usage=cached_comp.raw_usage_available,
            )

            request_record = GatewayRequestRecord(
                id=req_id,
                trace_id=trace_id,
                request_id=request_id,
                created_at=start_time,
                completed_at=time.time(),
                environment=settings.APP_ENV,
                gateway_version="0.1.0",
                api_version="v1",
                routing_policy=routing_decision.policy_name,
                routing_policy_version=routing_decision.policy_version,
                status="success",
                cache_status="hit",
                final_provider=provider_name,
                final_model_alias=model_alias,
                fallback_used=False,
                latency_ms=total_latency,
                prompt_fingerprint=prompt_fp,
                metadata=request.metadata or {},
            )

            try:
                await self.repository.record_request(request_record)
                await self.repository.record_decision(cache_decision, req_id)
            except Exception as repo_err:
                logger.warning(f"Telemetry persistence degraded: {repo_err}")

            default_metrics.record_request(
                policy=routing_decision.policy_name,
                model=model_alias,
                status="success",
                input_tokens=cached_comp.input_tokens,
                output_tokens=cached_comp.output_tokens,
                cost_usd=cost_res.estimated_cost or 0.0,
                latency_ms=total_latency,
                cached=True,
                fallback_used=False,
            )

            choice = ChatChoice(
                index=0,
                message=ChoiceMessage(role="assistant", content=cached_comp.content),
                finish_reason=cached_comp.finish_reason,
            )
            return ChatCompletionResponse(
                id=req_id,
                object="gateway.completion",
                created=int(start_time),
                model=model_alias,
                provider=provider_name,
                choices=[choice],
                usage=UsageSchema(
                    input_tokens=cached_comp.input_tokens,
                    output_tokens=cached_comp.output_tokens,
                    total_tokens=cached_comp.total_tokens,
                    cost_estimate=cost_res.estimated_cost,
                    currency=cost_res.currency,
                    cost_status=cost_res.cost_status,
                ),
                routing=RoutingDecisionSchema(
                    policy=routing_decision.policy_name,
                    policy_version=routing_decision.policy_version,
                    tier=tier,
                    reason=cache_decision.reason_message,
                    fallback_used=False,
                    complexity=routing_decision.complexity,
                    strategy=routing_decision.strategy,
                    task_category=routing_decision.task_category,
                    alternative_eligible_models=routing_decision.alternative_eligible_models,
                    estimated_cost=0.0,
                    bandit_score=routing_decision.bandit_score,
                    agentic_plan=routing_decision.agentic_plan,
                    classification_level=routing_decision.classification_level,
                    agent=routing_decision.agent,
                    mock_mode=routing_decision.mock_mode,
                ),
                latency_ms=total_latency,
                trace_id=trace_id,
                cached=True,
            )

        # 4. Multi-Model Collaboration or Sequential Candidate Execution
        deadline = DeadlineTracker(settings.REQUEST_TIMEOUT_SECONDS)
        total_attempt_number = 0
        completion: Optional[NormalizedCompletion] = None
        fallback_used = False
        final_model_alias = model_alias
        last_error: Optional[Exception] = None
        executed_plan_summary = routing_decision.agentic_plan

        # Check if plan dictates collaborative multi-model execution
        if (
            routing_decision.agentic_plan
            and routing_decision.agentic_plan.get("mode") == "collaborative"
            and not adapter_override
        ):
            try:
                # Reconstruct plan steps
                plan_obj = AgenticPlan(
                    mode=routing_decision.agentic_plan["mode"],
                    strategy=routing_decision.agentic_plan["strategy"],
                    steps=[
                        ExecutionStep(
                            step_number=s["step_number"],
                            title=s["title"],
                            action=s["action"],
                            assigned_model=s["assigned_model"],
                        )
                        for s in routing_decision.agentic_plan.get("steps", [])
                    ],
                )
                completion, executed_steps = await CollaborationExecutionEngine.execute_plan(
                    plan=plan_obj,
                    messages=domain_messages,
                    parameters=params,
                    adapter=adapter,
                    timeout_seconds=min(25.0, deadline.remaining_seconds),
                )
                final_model_alias = completion.model_alias
                executed_plan_summary = {
                    "mode": plan_obj.mode,
                    "strategy": plan_obj.strategy,
                    "total_steps": len(executed_steps),
                    "steps": [s.to_dict() for s in executed_steps],
                }
            except Exception as collab_err:
                logger.warning(f"Collaboration execution error ({collab_err}); falling back to single model: {model_alias}")
                completion = None

        # Fallback or Direct candidate progression execution
        if completion is None:
            models_to_try = [(model_alias, False)]
            seen_candidates = {model_alias}
            if routing_decision.candidate_progression:
                for cand in routing_decision.candidate_progression:
                    if cand not in seen_candidates:
                        models_to_try.append((cand, True))
                        seen_candidates.add(cand)
            elif settings.FALLBACK_MODEL_ALIAS != model_alias:
                models_to_try.append((settings.FALLBACK_MODEL_ALIAS, True))

            for current_model, is_fallback in models_to_try:
                if completion is not None:
                    break
                if is_fallback and deadline.is_expired:
                    break

                max_stage_attempts = 2
                stage_attempts = 0

                while stage_attempts < max_stage_attempts and not deadline.is_expired:
                    stage_attempts += 1
                    total_attempt_number += 1
                    attempt_id = generate_id("att")
                    attempt_start = time.time()
                    attempt_status = "success"
                    error_cat: Optional[str] = None
                    http_st: Optional[int] = 200
                    retry_after_s: Optional[float] = None

                    try:
                        # Pass user_id so BYOK credentials can be resolved
                        if hasattr(adapter, "generate"):
                            try:
                                completion = await adapter.generate(
                                    messages=domain_messages,
                                    parameters=params,
                                    model_alias=current_model,
                                    timeout_seconds=min(10.0, deadline.remaining_seconds),
                                    tools=request.tools,
                                    user_id=user_id,
                                )
                            except TypeError:
                                completion = await adapter.generate(
                                    messages=domain_messages,
                                    parameters=params,
                                    model_alias=current_model,
                                    timeout_seconds=min(10.0, deadline.remaining_seconds),
                                    tools=request.tools,
                                )
                        final_model_alias = current_model
                        fallback_used = is_fallback
                        break
                    except GatewayError as ge:
                        last_error = ge
                        attempt_status = "failure"
                        error_cat = ge.error_type
                        http_st = ge.status_code
                        if hasattr(ge, "retry_after_s"):
                            retry_after_s = ge.retry_after_s
                        if not is_retryable_error(ge) or deadline.is_expired:
                            break
                        delay = calculate_backoff(stage_attempts, retry_after_s=retry_after_s)
                        await asyncio.sleep(min(delay, deadline.remaining_seconds))
                    except Exception as ex:
                        last_error = ex
                        attempt_status = "failure"
                        error_cat = "provider_server_error"
                        http_st = 502
                        if deadline.is_expired:
                            break
                        delay = calculate_backoff(stage_attempts)
                        await asyncio.sleep(min(delay, deadline.remaining_seconds))
                    finally:
                        attempt_end = time.time()
                        attempt_rec = ProviderAttemptRecord(
                            id=attempt_id,
                            gateway_request_id=req_id,
                            attempt_number=total_attempt_number,
                            provider=provider_name,
                            model_alias=current_model,
                            started_at=attempt_start,
                            completed_at=attempt_end,
                            latency_ms=int((attempt_end - attempt_start) * 1000),
                            status=attempt_status,  # type: ignore
                            error_category=error_cat,
                            http_status=http_st,
                            is_fallback=is_fallback,
                            provider_request_id=completion.provider_request_id if completion else None,
                        )
                        try:
                            await self.repository.record_attempt(attempt_rec)
                        except Exception as err:
                            logger.warning(f"Telemetry degraded recording attempt: {err}")

        total_latency = int((time.time() - start_time) * 1000)

        # 5. Inline Response Evaluation & Quality Safeguards
        evaluation_result: Optional[InlineEvaluationResult] = None
        if completion and completion.content:
            expected_fmt = "json" if format_json else "markdown"
            evaluation_result = ResponseQualityEvaluator.evaluate(
                prompt_messages=domain_messages,
                response_text=completion.content,
                expected_format=expected_fmt,
                quality_threshold=request.routing.quality_threshold or 0.65,
            )

        # 6. Final Decision & Fallback Provenance
        fallback_reason = None
        final_tier = tier
        if fallback_used:
            fallback_reason = f"Primary model '{model_alias}' failed; recovered via candidate '{final_model_alias}'"
            meta = self.router.registry.get_model(final_model_alias)
            if meta:
                final_tier = meta.tier
            elif final_model_alias == settings.STRONG_MODEL_ALIAS:
                final_tier = "strong"

        final_decision = RoutingDecision(
            policy_name=routing_decision.policy_name,
            policy_version=routing_decision.policy_version,
            tier=final_tier,
            selected_model_alias=final_model_alias,
            selected_provider=provider_name,
            reason_code="FALLBACK" if fallback_used else routing_decision.reason_code,
            reason_message=f"{routing_decision.reason_message} (fallback used: {fallback_used})" if fallback_used else routing_decision.reason_message,
            feature_summary=routing_decision.feature_summary,
            fallback_used=fallback_used,
            complexity=routing_decision.complexity,
            strategy=routing_decision.strategy,
            task_category=routing_decision.task_category,
            alternative_eligible_models=routing_decision.alternative_eligible_models,
            estimated_cost=routing_decision.estimated_cost,
            fallback_reason=fallback_reason,
            candidate_progression=routing_decision.candidate_progression,
            bandit_score=routing_decision.bandit_score,
            agentic_plan=executed_plan_summary,
            evaluation=evaluation_result.to_dict() if evaluation_result else None,
            classification_level=routing_decision.classification_level,
            agent="Weak Agent" if final_tier == "cheap" else "Strong Agent",
            mock_mode=getattr(completion, "is_mock", False) if completion else False,
        )

        request_record = GatewayRequestRecord(
            id=req_id,
            trace_id=trace_id,
            request_id=request_id,
            created_at=start_time,
            completed_at=time.time(),
            environment=settings.APP_ENV,
            gateway_version="0.1.0",
            api_version="v1",
            routing_policy=routing_decision.policy_name,
            routing_policy_version=routing_decision.policy_version,
            status="success" if completion else "error",
            error_category=getattr(last_error, "error_type", "provider_unavailable") if not completion else None,
            cache_status="miss",
            final_provider=provider_name,
            final_model_alias=final_model_alias,
            fallback_used=fallback_used,
            latency_ms=total_latency,
            prompt_fingerprint=prompt_fp,
            metadata=request.metadata or {},
        )

        cost_res = None
        if completion:
            cost_res = self.cost_calculator.calculate(
                model_alias=final_model_alias,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                is_provider_usage=completion.raw_usage_available,
            )

            # Reconcile actual spend in budget controller
            actual_cost = cost_res.estimated_cost or 0.0
            default_budget_controller.record_spend(user_id=user_id, project_id=project_id, actual_cost=actual_cost)

            # Contextual Bandit Reinforcement Learning update
            if routing_decision.task_category:
                eval_score = evaluation_result.overall_score if evaluation_result else 0.85
                default_bandit_router.record_feedback(
                    category=routing_decision.task_category,
                    model_alias=final_model_alias,
                    quality_score=eval_score,
                    latency_ms=total_latency,
                    cost=actual_cost,
                    success=True,
                    fallback_used=fallback_used,
                )

        try:
            await self.repository.record_request(request_record)
            await self.repository.record_decision(final_decision, req_id)
            if completion and cost_res:
                usage_record = UsageRecord(
                    gateway_request_id=req_id,
                    provider_attempt_id=attempt_id,
                    input_tokens=completion.input_tokens,
                    output_tokens=completion.output_tokens,
                    total_tokens=completion.total_tokens,
                    usage_source="provider" if completion.raw_usage_available else "estimated",
                    rate_card_id=cost_res.rate_card_id,
                    input_rate=cost_res.input_rate,
                    output_rate=cost_res.output_rate,
                    estimated_cost=cost_res.estimated_cost,
                    currency=cost_res.currency,
                    cost_status=cost_res.cost_status,
                )
                await self.repository.record_usage(usage_record)
        except Exception as repo_err:
            logger.warning(f"Telemetry degraded: {repo_err}")

        if not completion:
            span.finish(status="ERROR")
            if isinstance(last_error, GatewayError):
                last_error.trace_id = trace_id
                raise last_error
            raise ProviderUnavailableError("All attempts and fallback failed to produce completion", trace_id=trace_id)

        # Populate Two-Tier Cache on Success
        if cache_eligible and cache_key:
            await self.cache_service.set(cache_key, completion, settings.CACHE_TTL_SECONDS)
            await default_semantic_cache.set(
                tenant_id=user_id,
                model_alias=final_model_alias,
                messages=domain_messages,
                parameters=params,
                completion=completion,
                ttl_seconds=settings.CACHE_TTL_SECONDS,
            )

        default_metrics.record_request(
            policy=final_decision.policy_name,
            model=final_model_alias,
            status="success",
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            cost_usd=cost_res.estimated_cost if cost_res and cost_res.estimated_cost else 0.0,
            latency_ms=total_latency,
            cached=False,
            fallback_used=fallback_used,
        )

        span.finish(status="OK")
        choice = ChatChoice(
            index=0,
            message=ChoiceMessage(role="assistant", content=completion.content, tool_calls=completion.tool_calls),
            finish_reason=completion.finish_reason,
        )

        return ChatCompletionResponse(
            id=req_id,
            object="gateway.completion",
            created=int(start_time),
            model=final_model_alias,
            provider=provider_name,
            choices=[choice],
            usage=UsageSchema(
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                total_tokens=completion.total_tokens,
                cost_estimate=cost_res.estimated_cost if cost_res else None,
                currency=cost_res.currency if cost_res else "USD",
                cost_status=cost_res.cost_status if cost_res else "unavailable",
            ),
            routing=RoutingDecisionSchema(
                policy=final_decision.policy_name,
                policy_version=final_decision.policy_version,
                tier=final_decision.tier,
                reason=final_decision.reason_message,
                fallback_used=fallback_used,
                complexity=final_decision.complexity,
                strategy=final_decision.strategy,
                task_category=final_decision.task_category,
                alternative_eligible_models=final_decision.alternative_eligible_models,
                estimated_cost=final_decision.estimated_cost,
                fallback_reason=fallback_reason,
                bandit_score=final_decision.bandit_score,
                agentic_plan=final_decision.agentic_plan,
                evaluation=final_decision.evaluation,
                classification_level=final_decision.classification_level,
                agent=final_decision.agent,
                mock_mode=final_decision.mock_mode,
            ),
            latency_ms=total_latency,
            trace_id=trace_id,
            cached=False,
        )
