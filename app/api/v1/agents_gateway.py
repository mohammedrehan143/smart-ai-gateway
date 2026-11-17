"""FastAPI Endpoints for Multi-Agent Configuration, Real Gateway Execution, and Analytics."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents import (
    default_credential_manager,
    default_execution_engine,
    default_provider_manager,
    default_router,
)
from app.api.deps import verify_gateway_auth

router = APIRouter(tags=["Agents & Gateway"])


# ---------------------------------------------------------------------------
# Pydantic Request / Response Schemas
# ---------------------------------------------------------------------------

class AgentConfigureRequest(BaseModel):
    agent_type: Literal["weak", "strong"] = Field(..., description="Agent tier to configure: weak or strong")
    provider: str = Field(..., description="Provider name: openai, groq, google, anthropic, openai_compatible")
    api_key: str = Field(..., min_length=3, description="Provider API key to securely encrypt and store")
    model_id: str = Field(..., min_length=1, description="Model ID (e.g. llama-3.1-8b-instant, gpt-4o)")
    base_url: Optional[str] = Field(None, description="Custom endpoint base URL if applicable")
    temperature: float = Field(0.2, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(1024, ge=1, le=128000, description="Maximum completion tokens")
    is_enabled: bool = Field(True, description="Whether agent is active")


class AgentTestRequest(BaseModel):
    provider: str = Field(..., description="Provider name")
    api_key: Optional[str] = Field(None, description="API key to test (if omitted, uses saved key)")
    model_id: str = Field(..., description="Model ID to test")
    base_url: Optional[str] = Field(None, description="Custom endpoint base URL")
    agent_type: Optional[Literal["weak", "strong"]] = Field(None, description="Optional agent type to test saved key")


class GatewayExecuteRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="User prompt to classify, route, and execute")
    mode: Literal["adaptive", "weak", "strong"] = Field("adaptive", description="Routing mode: adaptive, weak, strong")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1)
    conversation_history: Optional[List[Dict[str, str]]] = Field(None, description="Multi-turn conversation context")


# ---------------------------------------------------------------------------
# 1. Agent Configuration Endpoints (/api/agents)
# ---------------------------------------------------------------------------

@router.post(
    "/api/agents/configure",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
    summary="Configure Weak or Strong Agent with provider, encrypted API key, and model parameters",
)
async def configure_agent(
    payload: AgentConfigureRequest,
    x_user_id: Optional[str] = Header("default_user", alias="X-User-ID"),
) -> Dict[str, Any]:
    user_id = x_user_id or "default_user"
    config = default_credential_manager.store_agent_config(
        user_id=user_id,
        agent_type=payload.agent_type,
        provider=payload.provider,
        api_key=payload.api_key,
        model_id=payload.model_id,
        base_url=payload.base_url,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        is_enabled=payload.is_enabled,
    )
    return {
        "status": "configured",
        "agent": config.to_safe_dict(),
    }


@router.get(
    "/api/agents/config",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
    summary="Get current configurations for Weak and Strong Agents (with masked credentials)",
)
async def get_agent_configurations(
    x_user_id: Optional[str] = Header("default_user", alias="X-User-ID"),
) -> Dict[str, Any]:
    user_id = x_user_id or "default_user"
    configs = default_credential_manager.list_agent_configs(user_id)
    return {
        "user_id": user_id,
        "agents": configs,
    }


@router.post(
    "/api/agents/test",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
    summary="Test connectivity with a model provider using real API request probe",
)
async def test_agent_connection(
    payload: AgentTestRequest,
    x_user_id: Optional[str] = Header("default_user", alias="X-User-ID"),
) -> Dict[str, Any]:
    user_id = x_user_id or "default_user"
    api_key = payload.api_key

    # If api_key not provided or masked, fetch from saved config
    if not api_key or "..." in api_key or api_key == "********":
        if payload.agent_type:
            saved = default_credential_manager.get_agent_config(user_id, payload.agent_type)
            if saved:
                api_key = saved.get_plaintext_key()
                if not payload.base_url:
                    payload.base_url = saved.base_url

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API Key is required to test connection.",
        )

    res = await default_provider_manager.test_connection(
        provider=payload.provider,
        api_key=api_key,
        model_id=payload.model_id,
        base_url=payload.base_url,
    )
    return res


@router.delete(
    "/api/agents/config",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
    summary="Delete or reset Weak Agent, Strong Agent, or all agent configurations",
)
async def delete_agent_configuration(
    agent_type: Optional[Literal["weak", "strong"]] = Query(None, description="Specific agent type to delete"),
    x_user_id: Optional[str] = Header("default_user", alias="X-User-ID"),
) -> Dict[str, Any]:
    user_id = x_user_id or "default_user"
    deleted = default_credential_manager.delete_agent_config(user_id, agent_type)
    return {
        "status": "deleted" if deleted else "not_found",
        "agent_type": agent_type or "all",
    }


# ---------------------------------------------------------------------------
# 2. Real Gateway Execution Endpoints (/api/gateway)
# ---------------------------------------------------------------------------

@router.post(
    "/api/gateway/execute",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
    summary="Classify, route, and execute prompt using the appropriate agent with fallback",
)
async def execute_gateway_prompt(
    payload: GatewayExecuteRequest,
    x_user_id: Optional[str] = Header("default_user", alias="X-User-ID"),
) -> Dict[str, Any]:
    user_id = x_user_id or "default_user"
    res = await default_execution_engine.execute_prompt(
        user_id=user_id,
        prompt=payload.prompt,
        mode=payload.mode,
        conversation_history=payload.conversation_history,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    return res.to_dict()


@router.post(
    "/api/gateway/stream",
    dependencies=[Depends(verify_gateway_auth)],
    summary="Stream real-time token execution over Server-Sent Events",
)
async def stream_gateway_prompt(
    payload: GatewayExecuteRequest,
    x_user_id: Optional[str] = Header("default_user", alias="X-User-ID"),
):
    user_id = x_user_id or "default_user"
    generator = default_execution_engine.stream_prompt(
        user_id=user_id,
        prompt=payload.prompt,
        mode=payload.mode,
        conversation_history=payload.conversation_history,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    return StreamingResponse(generator, media_type="text/event-stream")


@router.get(
    "/api/gateway/history",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
    summary="Retrieve execution history records",
)
async def get_gateway_history(
    limit: int = Query(50, ge=1, le=200),
) -> List[Dict[str, Any]]:
    return default_execution_engine.get_history(limit=limit)


# ---------------------------------------------------------------------------
# 3. Analytics Endpoints (/api/analytics)
# ---------------------------------------------------------------------------

@router.get(
    "/api/analytics/overview",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
    summary="Retrieve aggregated platform performance, routing distribution, and cost savings analytics",
)
async def get_analytics_overview() -> Dict[str, Any]:
    return default_execution_engine.get_analytics_overview()


@router.get(
    "/api/analytics/usage",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
    summary="Retrieve usage statistics breakdown",
)
async def get_analytics_usage() -> Dict[str, Any]:
    overview = default_execution_engine.get_analytics_overview()
    history = default_execution_engine.get_history(limit=50)
    return {
        "overview": overview,
        "recent_executions_count": len(history),
        "history": history[:15],
    }
