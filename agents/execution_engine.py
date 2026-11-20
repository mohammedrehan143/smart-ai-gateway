"""Core Agent Execution Engine coordinating Routing, Dispatch, Retries, Fallback, and Telemetry."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional

from agents.credential_manager import CredentialManager, default_credential_manager
from agents.router import IntelligentRouter, RoutingDecision, default_router
from agents.strong_agent import StrongAgent, default_strong_agent
from agents.weak_agent import AgentExecutionResult, WeakAgent, default_weak_agent
from app.api.deps import get_repository
from app.core.config import settings
from app.core.errors import InvalidRequestError, StrongModelUnavailableError
from app.core.logging import get_logger
from app.domain.entities import (
    GatewayRequestRecord,
    UsageRecord,
    generate_id,
)
from app.domain.modes import GatewayMode, normalize_gateway_mode

logger = get_logger("agents.execution_engine")


@dataclass
class GatewayExecutionResponse:
    id: str
    prompt: str
    response: str
    agent: Literal["weak", "strong"]
    provider: str
    model: str
    routing: Dict[str, Any]
    tokens: Dict[str, int]
    cost: float
    latency_ms: int
    success: bool = True
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    selected_mode: str = "auto"
    classification_level: int = 1
    routing_reason: str = ""
    actual_provider: str = ""
    actual_model: str = ""
    reasoning_effort: str = "none"
    fallback_status: str = "not_triggered"
    mock_mode: bool = False

    def to_dict(self) -> Dict[str, Any]:
        actual_prov = self.actual_provider or self.provider
        actual_mod = self.actual_model or self.model
        reason = self.routing_reason or (self.routing.get("reason", "") if self.routing else "")
        mode = self.selected_mode or (self.routing.get("selected_mode", "auto") if self.routing else "auto")
        level = self.classification_level or (self.routing.get("complexity", 1) if self.routing else 1)
        effort = self.reasoning_effort or (self.routing.get("reasoning_effort", "none") if self.routing else "none")
        fb_status = self.fallback_status or (
            self.routing.get("fallback_status", "not_triggered") if self.routing else "not_triggered"
        )

        return {
            "id": self.id,
            "prompt": self.prompt,
            "response": self.response,
            "agent": self.agent,
            "provider": actual_prov,
            "model": actual_mod,
            # Transparency fields
            "selected_mode": mode,
            "classification_level": level,
            "routing_reason": reason,
            "actual_provider": actual_prov,
            "actual_model": actual_mod,
            "reasoning_effort": effort,
            "fallback_status": fb_status,
            "latency": self.latency_ms,
            "latency_ms": self.latency_ms,
            "token_usage": self.tokens,
            "tokens": self.tokens,
            "estimated_cost": round(self.cost, 6),
            "cost": round(self.cost, 6),
            "mock_mode": self.mock_mode,
            "routing": self.routing,
            "success": self.success,
            "error": self.error,
            "created_at": self.created_at,
        }

    @property
    def token_usage(self) -> Dict[str, int]:
        return self.tokens

    @property
    def is_mock(self) -> bool:
        return self.mock_mode

    @property
    def estimated_cost(self) -> float:
        return self.cost


class ExecutionEngine:
    """Production execution orchestrator managing real agent dispatch with automated fallback and metrics."""

    def __init__(
        self,
        router: Optional[IntelligentRouter] = None,
        weak_agent: Optional[WeakAgent] = None,
        strong_agent: Optional[StrongAgent] = None,
        credential_mgr: Optional[CredentialManager] = None,
    ):
        self.router = router or default_router
        self.weak_agent = weak_agent or default_weak_agent
        self.strong_agent = strong_agent or default_strong_agent
        self.credential_mgr = credential_mgr or default_credential_manager
        # In-memory execution log buffer (supplemented by SQLite)
        self._history: List[GatewayExecutionResponse] = []

    async def execute_prompt(
        self,
        user_id: str,
        prompt: str,
        mode: str = "auto",
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_retries: int = 1,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> GatewayExecutionResponse:
        """Executes prompt with intelligent routing, retries, and fallback to alternate agent.

        Enforces priority: Explicit Expert Mode > Explicit Strong Mode > Explicit Fast/Balanced Mode > Auto Classification.
        """
        req_id = generate_id("greq")
        start_time = time.time()

        if not prompt or not prompt.strip():
            raise InvalidRequestError("Prompt cannot be empty.")

        # 1. Resolve mode from request or persistent session configuration
        effective_mode_str = mode
        if not effective_mode_str:
            session_mode = self.credential_mgr.get_session_mode(user_id)
            if session_mode:
                effective_mode_str = session_mode
        norm_mode = normalize_gateway_mode(effective_mode_str)

        # 2. Routing classification
        manual_override: Optional[Literal["weak", "strong"]] = None
        if norm_mode == GatewayMode.STRONG:
            manual_override = "strong"
        elif norm_mode == GatewayMode.FAST:
            manual_override = "weak"

        decision: RoutingDecision = self.router.classify_and_route(
            prompt=prompt,
            conversation_history=conversation_history,
            manual_agent=manual_override,
            mode=norm_mode.value,
        )

        chosen_agent_type = decision.agent
        is_strong_override = norm_mode in (GatewayMode.STRONG, GatewayMode.EXPERT)
        if is_strong_override:
            chosen_agent_type = "strong"

        # 3. Provider validation for Strong Mode / Strong Agent
        if chosen_agent_type == "strong":
            if not self.strong_agent.is_configured(user_id):
                from app.providers.resolver import is_mock_mode_explicitly_enabled

                if is_mock_mode_explicitly_enabled():
                    # In test/mock environment, configure mock-strong default
                    cfg = self.credential_mgr.get_agent_config(user_id, "strong")
                    if not cfg:
                        self.credential_mgr.store_agent_config(
                            user_id=user_id,
                            agent_type="strong",
                            provider="mock",
                            api_key="mock_strong_key_test",
                            model_id="mock-strong",
                        )
                else:
                    total_latency_ms = int((time.time() - start_time) * 1000)
                    routing_dict = decision.to_dict()
                    routing_dict["fallback_status"] = (
                        "prohibited_in_strong_mode" if is_strong_override else "unconfigured_strong_agent"
                    )
                    err_resp = GatewayExecutionResponse(
                        id=req_id,
                        prompt=prompt,
                        response="",
                        agent="strong",
                        provider="unconfigured",
                        model="unconfigured",
                        routing=routing_dict,
                        tokens={"prompt": 0, "completion": 0, "total": 0},
                        cost=0.0,
                        latency_ms=total_latency_ms,
                        success=False,
                        error="Strong Agent API key is not configured. Please configure your Strong Agent provider and API key in Agent Settings (or run 'smartai login' / set OPENAI_API_KEY).",
                        selected_mode=norm_mode.value,
                        classification_level=decision.complexity,
                        routing_reason=decision.reason,
                        actual_provider="unconfigured",
                        actual_model="unconfigured",
                        reasoning_effort="high",
                        fallback_status=routing_dict["fallback_status"],
                        mock_mode=False,
                    )
                    await self._record_telemetry(user_id, err_resp)
                    return err_resp

        fallback_agent_obj = self.strong_agent if chosen_agent_type == "weak" else self.weak_agent
        fallback_type: Literal["weak", "strong"] = "strong" if chosen_agent_type == "weak" else "weak"

        result: Optional[AgentExecutionResult] = None
        execution_error: Optional[Exception] = None
        fallback_used = False
        fallback_reason: Optional[str] = None
        actual_agent_type = chosen_agent_type

        # 4. Primary agent execution with retry
        timeout_s = getattr(settings, "REQUEST_TIMEOUT_SECONDS", 30.0)
        for attempt in range(max_retries + 1):
            try:
                if chosen_agent_type == "strong":
                    result = await asyncio.wait_for(
                        self.strong_agent.execute(
                            user_id=user_id,
                            prompt=prompt,
                            conversation_history=conversation_history,
                            temperature_override=temperature,
                            max_tokens_override=max_tokens,
                            reasoning_effort="high" if is_strong_override else decision.reasoning_effort,
                            tools=tools,
                        ),
                        timeout=timeout_s,
                    )
                else:
                    result = await asyncio.wait_for(
                        self.weak_agent.execute(
                            user_id=user_id,
                            prompt=prompt,
                            conversation_history=conversation_history,
                            temperature_override=temperature,
                            max_tokens_override=max_tokens,
                        ),
                        timeout=timeout_s,
                    )
                break
            except Exception as exc:
                execution_error = exc
                logger.warning(f"Agent execution attempt {attempt + 1} failed for {chosen_agent_type}: {exc}")
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))

        # 5. Fallback Handling
        if result is None:
            # If Strong Agent was chosen (or Strong Mode override), NEVER fall back to Weak Agent!
            if chosen_agent_type == "strong" or is_strong_override:
                total_latency_ms = int((time.time() - start_time) * 1000)
                cfg = self.credential_mgr.get_agent_config(user_id, "strong")
                is_mock = (cfg.provider == "mock" or "mock" in cfg.model_id.lower()) if cfg else False
                actual_prov = "mock" if is_mock else (cfg.provider if cfg else "unknown")
                actual_mod = cfg.model_id if cfg else "unknown"
                routing_dict = decision.to_dict()
                routing_dict["fallback_status"] = "prohibited_in_strong_mode"
                routing_dict["fallback_used"] = False

                err_resp = GatewayExecutionResponse(
                    id=req_id,
                    prompt=prompt,
                    response="",
                    agent="strong",
                    provider=actual_prov,
                    model=actual_mod,
                    routing=routing_dict,
                    tokens={"prompt": 0, "completion": 0, "total": 0},
                    cost=0.0,
                    latency_ms=total_latency_ms,
                    success=False,
                    error=f"Strong Agent execution failed: {execution_error}",
                    selected_mode=norm_mode.value,
                    classification_level=decision.complexity,
                    routing_reason=decision.reason,
                    actual_provider=actual_prov,
                    actual_model=actual_mod,
                    reasoning_effort="high",
                    fallback_status="prohibited_in_strong_mode",
                    mock_mode=is_mock,
                )
                await self._record_telemetry(user_id, err_resp)
                return err_resp

            # For Weak Agent failures in Auto/Fast mode, allow fallback to Strong Agent if configured
            if fallback_agent_obj.is_configured(user_id):
                fallback_reason = f"{chosen_agent_type.capitalize()} Agent encountered error: {execution_error}. Fallback to {fallback_type.capitalize()} Agent initiated."
                logger.info(fallback_reason)
                try:
                    result = await asyncio.wait_for(
                        fallback_agent_obj.execute(
                            user_id=user_id,
                            prompt=prompt,
                            conversation_history=conversation_history,
                            temperature_override=temperature,
                            max_tokens_override=max_tokens,
                        ),
                        timeout=timeout_s,
                    )
                    fallback_used = True
                    actual_agent_type = fallback_type
                except Exception as fallback_exc:
                    logger.error(f"Fallback to {fallback_type} Agent also failed: {fallback_exc}")
                    total_latency_ms = int((time.time() - start_time) * 1000)
                    err_resp = GatewayExecutionResponse(
                        id=req_id,
                        prompt=prompt,
                        response="",
                        agent=chosen_agent_type,
                        provider="unknown",
                        model="unknown",
                        routing=decision.to_dict(),
                        tokens={"prompt": 0, "completion": 0, "total": 0},
                        cost=0.0,
                        latency_ms=total_latency_ms,
                        success=False,
                        error=f"Both primary and fallback agents failed: {execution_error}; fallback error: {fallback_exc}",
                        selected_mode=norm_mode.value,
                        classification_level=decision.complexity,
                        routing_reason=decision.reason,
                        actual_provider="unknown",
                        actual_model="unknown",
                        reasoning_effort=decision.reasoning_effort,
                        fallback_status="fallback_failed",
                        mock_mode=False,
                    )
                    await self._record_telemetry(user_id, err_resp)
                    return err_resp
            else:
                total_latency_ms = int((time.time() - start_time) * 1000)
                err_resp = GatewayExecutionResponse(
                    id=req_id,
                    prompt=prompt,
                    response="",
                    agent=chosen_agent_type,
                    provider="unknown",
                    model="unknown",
                    routing=decision.to_dict(),
                    tokens={"prompt": 0, "completion": 0, "total": 0},
                    cost=0.0,
                    latency_ms=total_latency_ms,
                    success=False,
                    error=str(execution_error),
                    selected_mode=norm_mode.value,
                    classification_level=decision.complexity,
                    routing_reason=decision.reason,
                    actual_provider="unknown",
                    actual_model="unknown",
                    reasoning_effort=decision.reasoning_effort,
                    fallback_status="no_fallback_configured",
                    mock_mode=False,
                )
                await self._record_telemetry(user_id, err_resp)
                return err_resp

        # 6. Construct execution response with complete transparency
        is_mock = getattr(result, "is_mock", False) or (result.provider == "mock") or ("mock" in result.model.lower())
        actual_prov = "mock" if is_mock else result.provider
        actual_mod = result.model
        fb_status = "fallback_to_strong" if fallback_used else "not_triggered"

        routing_dict = decision.to_dict()
        routing_dict["fallback_used"] = fallback_used
        routing_dict["fallback_reason"] = fallback_reason
        routing_dict["fallback_status"] = fb_status
        routing_dict["actual_provider"] = actual_prov
        routing_dict["actual_model"] = actual_mod
        routing_dict["selected_mode"] = norm_mode.value
        routing_dict["reasoning_effort"] = getattr(result, "reasoning_effort", "none") or decision.reasoning_effort

        total_latency_ms = int((time.time() - start_time) * 1000)

        response = GatewayExecutionResponse(
            id=req_id,
            prompt=prompt,
            response=result.content,
            agent=actual_agent_type,
            provider=actual_prov,
            model=actual_mod,
            routing=routing_dict,
            tokens={
                "prompt": result.prompt_tokens,
                "completion": result.completion_tokens,
                "total": result.total_tokens,
            },
            cost=result.cost,
            latency_ms=total_latency_ms,
            success=True,
            selected_mode=norm_mode.value,
            classification_level=decision.complexity,
            routing_reason=decision.reason,
            actual_provider=actual_prov,
            actual_model=actual_mod,
            reasoning_effort=routing_dict["reasoning_effort"],
            fallback_status=fb_status,
            mock_mode=is_mock,
        )

        # 7. Record telemetry
        await self._record_telemetry(user_id, response)
        return response

    async def stream_prompt(
        self,
        user_id: str,
        prompt: str,
        mode: str = "auto",
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Streams real token chunks over SSE with initial routing metadata header."""
        req_id = generate_id("greq")
        start_time = time.time()

        effective_mode_str = mode
        if not effective_mode_str:
            session_mode = self.credential_mgr.get_session_mode(user_id)
            if session_mode:
                effective_mode_str = session_mode
        norm_mode = normalize_gateway_mode(effective_mode_str)

        manual_override: Optional[Literal["weak", "strong"]] = None
        if norm_mode == GatewayMode.STRONG:
            manual_override = "strong"
        elif norm_mode == GatewayMode.FAST:
            manual_override = "weak"

        decision = self.router.classify_and_route(
            prompt=prompt,
            conversation_history=conversation_history,
            manual_agent=manual_override,
            mode=norm_mode.value,
        )

        is_strong_override = norm_mode in (GatewayMode.STRONG, GatewayMode.EXPERT)
        chosen_agent_type = "strong" if is_strong_override else decision.agent

        if chosen_agent_type == "strong" and not self.strong_agent.is_configured(user_id):
            from app.providers.resolver import is_mock_mode_explicitly_enabled

            if is_mock_mode_explicitly_enabled():
                cfg = self.credential_mgr.get_agent_config(user_id, "strong")
                if not cfg:
                    self.credential_mgr.store_agent_config(
                        user_id=user_id,
                        agent_type="strong",
                        provider="mock",
                        api_key="mock_strong_key_test",
                        model_id="mock-strong",
                    )
            else:
                raise StrongModelUnavailableError(
                    "Strong Agent API key is not configured. Please configure your Strong Agent provider and API key in Agent Settings (or run 'smartai login' / set OPENAI_API_KEY)."
                )

        agent_obj = self.strong_agent if chosen_agent_type == "strong" else self.weak_agent
        cfg = self.credential_mgr.get_agent_config(user_id, chosen_agent_type)
        is_mock = (cfg.provider == "mock" or "mock" in cfg.model_id.lower()) if cfg else False
        actual_prov = "mock" if is_mock else (cfg.provider if cfg else "configured")
        actual_mod = cfg.model_id if cfg else "stream_model"
        effort = "high" if is_strong_override else decision.reasoning_effort

        # Yield metadata header event with full transparency
        routing_dict = decision.to_dict()
        routing_dict["selected_mode"] = norm_mode.value
        routing_dict["actual_provider"] = actual_prov
        routing_dict["actual_model"] = actual_mod
        routing_dict["reasoning_effort"] = effort
        routing_dict["fallback_status"] = "not_triggered"

        init_event = {
            "type": "routing",
            "id": req_id,
            "agent": chosen_agent_type,
            "selected_mode": norm_mode.value,
            "classification_level": decision.complexity,
            "routing_reason": decision.reason,
            "actual_provider": actual_prov,
            "actual_model": actual_mod,
            "reasoning_effort": effort,
            "fallback_status": "not_triggered",
            "mock_mode": is_mock,
            "routing": routing_dict,
        }
        yield f"data: {json.dumps(init_event)}\n\n"

        full_content = ""
        prompt_tokens_est = max(1, len(prompt.split()))

        try:
            async for chunk in agent_obj.stream_execute(
                user_id=user_id,
                prompt=prompt,
                conversation_history=conversation_history,
                temperature_override=temperature,
                max_tokens_override=max_tokens,
            ):
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content_piece = delta.get("content")
                    if content_piece:
                        full_content += content_piece
                        yield f"data: {json.dumps({'type': 'token', 'content': content_piece})}\n\n"

            elapsed_ms = int((time.time() - start_time) * 1000)
            completion_tokens_est = max(1, len(full_content.split()))
            cost = agent_obj.calculate_cost(prompt_tokens_est, completion_tokens_est, chosen_agent_type)

            final_event = {
                "type": "done",
                "id": req_id,
                "agent": chosen_agent_type,
                "selected_mode": norm_mode.value,
                "classification_level": decision.complexity,
                "routing_reason": decision.reason,
                "actual_provider": actual_prov,
                "actual_model": actual_mod,
                "reasoning_effort": effort,
                "fallback_status": "not_triggered",
                "latency_ms": elapsed_ms,
                "latency": elapsed_ms,
                "token_usage": {
                    "prompt": prompt_tokens_est,
                    "completion": completion_tokens_est,
                    "total": prompt_tokens_est + completion_tokens_est,
                },
                "tokens": {
                    "prompt": prompt_tokens_est,
                    "completion": completion_tokens_est,
                    "total": prompt_tokens_est + completion_tokens_est,
                },
                "estimated_cost": round(cost, 6),
                "cost": round(cost, 6),
                "mock_mode": is_mock,
            }
            yield f"data: {json.dumps(final_event)}\n\n"
            yield "data: [DONE]\n\n"

            # Record in telemetry
            final_resp = GatewayExecutionResponse(
                id=req_id,
                prompt=prompt,
                response=full_content,
                agent=chosen_agent_type,
                provider=actual_prov,
                model=actual_mod,
                routing=routing_dict,
                tokens={
                    "prompt": prompt_tokens_est,
                    "completion": completion_tokens_est,
                    "total": prompt_tokens_est + completion_tokens_est,
                },
                cost=cost,
                latency_ms=elapsed_ms,
                success=True,
                selected_mode=norm_mode.value,
                classification_level=decision.complexity,
                routing_reason=decision.reason,
                actual_provider=actual_prov,
                actual_model=actual_mod,
                reasoning_effort=effort,
                fallback_status="not_triggered",
                mock_mode=is_mock,
            )
            await self._record_telemetry(user_id, final_resp)

        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"

    async def _record_telemetry(self, user_id: str, resp: GatewayExecutionResponse) -> None:
        """Stores execution in both the fast buffer and SQLite repository."""
        self._history.append(resp)
        if len(self._history) > 100:
            self._history.pop(0)

        try:
            repo = await get_repository()
            req_record = GatewayRequestRecord(
                id=resp.id,
                trace_id=f"tr_{resp.id[5:]}",
                request_id=resp.id,
                created_at=resp.created_at,
                completed_at=resp.created_at + (resp.latency_ms / 1000.0),
                environment="production",
                gateway_version="2.0.0",
                api_version="v1",
                routing_policy=resp.routing.get("agent", "adaptive"),
                routing_policy_version="2.0",
                status="SUCCESS" if resp.success else "ERROR",
                error_category=None if resp.success else "PROVIDER_FAILURE",
                cache_status="BYPASS",
                final_provider=resp.provider,
                final_model_alias=resp.model,
                fallback_used=resp.routing.get("fallback_used", False),
                latency_ms=resp.latency_ms,
                prompt_fingerprint=str(hash(resp.prompt)),
                metadata={
                    "user_id": user_id,
                    "prompt": resp.prompt[:200],
                    "agent": resp.agent,
                    "cost": resp.cost,
                    "tokens": resp.tokens,
                },
            )
            await repo.record_request(req_record)

            # Record usage
            usage = UsageRecord(
                gateway_request_id=resp.id,
                input_tokens=resp.tokens.get("prompt", 0),
                output_tokens=resp.tokens.get("completion", 0),
                total_tokens=resp.tokens.get("total", 0),
                estimated_cost=resp.cost,
                currency="USD",
                cost_status="calculated" if resp.cost > 0 else "unavailable",
            )
            await repo.record_usage(usage)

        except Exception as e:
            logger.warning(f"Failed to persist trace to SQLite: {e}")

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent execution history."""
        return [r.to_dict() for r in reversed(self._history[-limit:])]

    def get_analytics_overview(self) -> Dict[str, Any]:
        """Calculates aggregated metrics, routing breakdown, and cost savings vs always strong."""
        total = len(self._history)
        if total == 0:
            return {
                "total_requests": 0,
                "weak_agent_requests": 0,
                "strong_agent_requests": 0,
                "success_rate": 1.0,
                "avg_latency_ms": 0,
                "total_tokens": 0,
                "estimated_total_cost": 0.0,
                "cost_savings_pct": 0.0,
                "estimated_savings_usd": 0.0,
                "routing_distribution": {"weak": 0.5, "strong": 0.5},
            }

        weak_count = sum(1 for r in self._history if r.agent == "weak")
        strong_count = sum(1 for r in self._history if r.agent == "strong")
        success_count = sum(1 for r in self._history if r.success)

        total_tokens = sum(r.tokens.get("total", 0) for r in self._history)
        total_cost = sum(r.cost for r in self._history)
        avg_latency = int(sum(r.latency_ms for r in self._history) / total)

        # Compute cost if all requests had executed on Strong Agent baseline
        # Baseline rates for Strong Agent: $2.50 input / $10.00 output
        hypothetical_strong_cost = 0.0
        for r in self._history:
            in_tok = r.tokens.get("prompt", 0)
            out_tok = r.tokens.get("completion", 0)
            hypothetical_strong_cost += (in_tok * (2.50 / 1_000_000.0)) + (out_tok * (10.00 / 1_000_000.0))

        savings_usd = max(0.0, hypothetical_strong_cost - total_cost)
        savings_pct = (
            round((savings_usd / hypothetical_strong_cost * 100.0), 1) if hypothetical_strong_cost > 0 else 0.0
        )

        return {
            "total_requests": total,
            "weak_agent_requests": weak_count,
            "strong_agent_requests": strong_count,
            "success_rate": round(success_count / total, 3),
            "avg_latency_ms": avg_latency,
            "total_tokens": total_tokens,
            "estimated_total_cost": round(total_cost, 6),
            "cost_savings_pct": savings_pct,
            "estimated_savings_usd": round(savings_usd, 6),
            "routing_distribution": {
                "weak": round(weak_count / total, 2),
                "strong": round(strong_count / total, 2),
            },
        }


default_execution_engine = ExecutionEngine()
