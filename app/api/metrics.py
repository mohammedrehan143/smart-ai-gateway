"""Prometheus metrics endpoint."""

from fastapi import APIRouter, Response
from app.core.metrics import default_metrics

router = APIRouter(tags=["Metrics"])


@router.get("/metrics", response_class=Response)
async def get_metrics():
    """Prometheus exposition format metrics."""
    return Response(content=default_metrics.export_prometheus(), media_type="text/plain; version=0.0.4")
