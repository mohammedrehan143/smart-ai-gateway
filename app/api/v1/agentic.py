"""Agentic Task Planning and Execution Graph API endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field

from app.api.deps import AuthenticatedUser, get_authenticated_user, get_orchestrator, verify_gateway_auth
from app.api.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessageSchema,
)
from app.core.config import settings
from app.domain.agentic_planner import default_agentic_planner
from app.domain.entities import ChatMessage
from app.domain.intent_engine import default_intent_engine
from app.services.orchestrator import ChatOrchestrator

router = APIRouter(prefix="/v1/agentic", tags=["Agentic"])


class PlanRequest(BaseModel):
    messages: List[ChatMessageSchema] = Field(..., min_length=1)
    tools: Optional[List[Dict[str, Any]]] = None
    collaboration_strategy: Optional[str] = Field(None, description="peer_review, code_verification, or consensus")
    force_collaboration: bool = False


class PlanResponse(BaseModel):
    mode: str
    strategy: str
    steps: List[Dict[str, Any]]
    total_steps: int
    rationale: str
    task_category: str
    complexity: str
    primary_model: str
    estimated_tokens: int


@router.post(
    "/plan",
    response_model=PlanResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
async def generate_agentic_plan(payload: PlanRequest) -> Dict[str, Any]:
    """Generates an explicit execution graph plan for a request without executing inference."""
    domain_msgs = [ChatMessage(role=m.role, content=m.content) for m in payload.messages]
    profile = default_intent_engine.analyze(domain_msgs, tools=payload.tools)

    cheap_model = settings.CHEAP_MODEL_ALIAS
    strong_model = settings.STRONG_MODEL_ALIAS
    primary_model = cheap_model if profile.complexity.value in ("SIMPLE", "MODERATE") else strong_model

    plan = default_agentic_planner.create_plan(
        profile=profile,
        primary_model=primary_model,
        strong_model=strong_model,
        cheap_model=cheap_model,
        collaboration_requested=payload.force_collaboration,
        collaboration_strategy=payload.collaboration_strategy,
    )

    return {
        "mode": plan.mode.value,
        "strategy": plan.strategy,
        "steps": [s.to_dict() for s in plan.steps],
        "total_steps": len(plan.steps),
        "rationale": plan.rationale,
        "task_category": profile.category.value,
        "complexity": profile.complexity.value,
        "primary_model": primary_model,
        "estimated_tokens": plan.estimated_total_tokens,
    }


@router.post(
    "/execute",
    response_model=ChatCompletionResponse,
    status_code=status.HTTP_200_OK,
)
async def execute_agentic_task(
    payload: ChatCompletionRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    orchestrator: ChatOrchestrator = Depends(get_orchestrator),
) -> ChatCompletionResponse:
    """Executes a request through the agentic orchestration graph with optional multi-model collaboration."""
    effective_user = x_user_id if (user.is_admin and x_user_id) else user.user_id
    if not payload.routing.user_id or not user.is_admin:
        payload.routing.user_id = effective_user

    # If calling /agentic/execute, enable collaboration by default if a strategy is requested
    if payload.routing.collaboration_strategy and not payload.routing.enable_collaboration:
        payload.routing.enable_collaboration = True

    return await orchestrator.execute_chat(request=payload)
