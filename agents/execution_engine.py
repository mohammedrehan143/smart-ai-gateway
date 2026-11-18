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
from app.core.errors import InvalidRequestError
from app.core.logging import get_logger
from app.domain.entities import (
    GatewayRequestRecord,
    UsageRecord,
    generate_id,
)

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "response": self.response,
            "agent": self.agent,
            "provider": self.provider,
            "model": self.model,
            "routing": self.routing,
            "tokens": self.tokens,
            "cost": round(self.cost, 6),
            "latency_ms": self.latency_ms,
            "success": self.success,
            "error": self.error,
            "created_at": self.created_at,
        }


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
        mode: Literal["adaptive", "weak", "strong"] = "adaptive",
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_retries: int = 1,
    ) -> GatewayExecutionResponse:
        """Executes prompt with intelligent routing, retries, and fallback to alternate agent."""
        req_id = generate_id("greq")
        start_time = time.time()

        if not prompt or not prompt.strip():
            raise InvalidRequestError("Prompt cannot be empty.")

        # 1. Routing classification
        manual_override: Optional[Literal["weak", "strong"]] = None
        if mode in ("weak", "strong"):
            manual_override = mode

        decision: RoutingDecision = self.router.classify_and_route(
            prompt=prompt,
            conversation_history=conversation_history,
            manual_agent=manual_override,
        )

        chosen_agent_type = decision.agent
        agent_obj = self.weak_agent if chosen_agent_type == "weak" else self.strong_agent
        fallback_agent_obj = self.strong_agent if chosen_agent_type == "weak" else self.weak_agent
        fallback_type: Literal["weak", "strong"] = "strong" if chosen_agent_type == "weak" else "weak"

        result: Optional[AgentExecutionResult] = None
        execution_error: Optional[Exception] = None
        fallback_used = False
        fallback_reason: Optional[str] = None
        actual_agent_type = chosen_agent_type

        # 2. Primary agent execution with retry
        timeout_s = getattr(settings, "REQUEST_TIMEOUT_SECONDS", 30.0)
        for attempt in range(max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    agent_obj.execute(
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

        # 3. Fallback to alternate agent if primary failed
        if result is None:
            # Check if fallback agent is configured
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
                )
                await self._record_telemetry(user_id, err_resp)
                return err_resp

        # 4. Construct execution response
        routing_dict = decision.to_dict()
        routing_dict["fallback_used"] = fallback_used
        routing_dict["fallback_reason"] = fallback_reason

        total_latency_ms = int((time.time() - start_time) * 1000)

        response = GatewayExecutionResponse(
            id=req_id,
            prompt=prompt,
            response=result.content,
            agent=actual_agent_type,
            provider=result.provider,
            model=result.model,
            routing=routing_dict,
            tokens={
                "prompt": result.prompt_tokens,
                "completion": result.completion_tokens,
                "total": result.total_tokens,
            },
            cost=result.cost,
            latency_ms=total_latency_ms,
            success=True,
        )

        # 5. Record telemetry
        await self._record_telemetry(user_id, response)
        return response

    async def stream_prompt(
        self,
        user_id: str,
        prompt: str,
        mode: Literal["adaptive", "weak", "strong"] = "adaptive",
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Streams real token chunks over SSE with initial routing metadata header."""
        req_id = generate_id("greq")
        start_time = time.time()

        manual_override: Optional[Literal["weak", "strong"]] = mode if mode in ("weak", "strong") else None
        decision = self.router.classify_and_route(
            prompt=prompt,
            conversation_history=conversation_history,
            manual_agent=manual_override,
        )

        agent_obj = self.weak_agent if decision.agent == "weak" else self.strong_agent
        agent_type = decision.agent

        # Yield metadata header event
        init_event = {
            "type": "routing",
            "id": req_id,
            "agent": agent_type,
            "routing": decision.to_dict(),
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
            cost = agent_obj.calculate_cost(prompt_tokens_est, completion_tokens_est, decision.agent)

            final_event = {
                "type": "done",
                "id": req_id,
                "agent": agent_type,
                "latency_ms": elapsed_ms,
                "tokens": {
                    "prompt": prompt_tokens_est,
                    "completion": completion_tokens_est,
                    "total": prompt_tokens_est + completion_tokens_est,
                },
                "cost": round(cost, 6),
            }
            yield f"data: {json.dumps(final_event)}\n\n"
            yield "data: [DONE]\n\n"

            # Record in telemetry
            final_resp = GatewayExecutionResponse(
                id=req_id,
                prompt=prompt,
                response=full_content,
                agent=agent_type,
                provider="configured",
                model="stream_model",
                routing=decision.to_dict(),
                tokens={
                    "prompt": prompt_tokens_est,
                    "completion": completion_tokens_est,
                    "total": prompt_tokens_est + completion_tokens_est,
                },
                cost=cost,
                latency_ms=elapsed_ms,
                success=True,
            )
            await self._record_telemetry(user_id, final_resp)

        except Exception as exc:
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
