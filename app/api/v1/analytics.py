"""Usage and Cost Analytics endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query, status
from app.api.deps import get_repository, verify_gateway_auth
from app.domain.interfaces import TraceRepository

router = APIRouter(prefix="/v1/analytics", tags=["Analytics"])


@router.get(
    "/usage",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
async def get_usage_analytics(
    since: Optional[float] = Query(None, description="Filter records starting from epoch seconds"),
    limit: int = Query(50, ge=1, le=500, description="Max recent requests to return"),
    repo: TraceRepository = Depends(get_repository),
) -> Dict[str, Any]:
    """Retrieves aggregated usage statistics including requests, tokens, latencies, and cache metrics."""
    summary = await repo.get_usage_summary(since_timestamp=since, limit=limit)
    return summary


@router.get(
    "/cost",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
async def get_cost_analytics(
    since: Optional[float] = Query(None, description="Filter records starting from epoch seconds"),
    repo: TraceRepository = Depends(get_repository),
) -> Dict[str, Any]:
    """Retrieves financial analytics including provider spend, model spend, and estimated savings."""
    summary = await repo.get_cost_summary(since_timestamp=since)
    return summary
