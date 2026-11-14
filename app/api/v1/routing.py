"""Routing decision inspection endpoint."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from app.api.deps import get_repository, verify_gateway_auth
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
