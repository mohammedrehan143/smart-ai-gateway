"""Routing decision inspection and adaptive bandit telemetry endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from app.api.deps import get_repository, verify_gateway_auth
from app.domain.bandit_router import default_bandit_router
from app.domain.interfaces import TraceRepository

router = APIRouter(prefix="/v1/routing", tags=["Routing"])


@router.get(
    "/decisions",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
async def get_routing_decisions(
    limit: int = Query(20, ge=1, le=100, description="Number of recent decisions"),
    trace_id: Optional[str] = Query(None, description="Filter by specific trace ID"),
    repo: TraceRepository = Depends(get_repository),
) -> Dict[str, Any]:
    """Retrieves recent routing decisions with extracted features and reasoning."""
    decisions: List[Dict[str, Any]] = await repo.get_recent_decisions(limit=limit)

    if trace_id:
        decisions = [d for d in decisions if d.get("trace_id") == trace_id]

    return {
        "decisions": decisions,
        "count": len(decisions),
    }


@router.get(
    "/bandit-stats",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
async def get_bandit_statistics() -> Dict[str, Any]:
    """Returns contextual bandit learning statistics across task categories and models."""
    stats = default_bandit_router.get_statistics()
    return {
        "arms": stats,
        "total_arms": len(stats),
        "exploration_rate": default_bandit_router.epsilon,
        "enabled": default_bandit_router.enabled,
    }


@router.post(
    "/bandit-reset",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
async def reset_bandit_statistics() -> Dict[str, Any]:
    """Resets all contextual bandit learning state back to baseline priors."""
    default_bandit_router.reset()
    return {"status": "reset", "message": "Bandit statistics reset to default priors."}
