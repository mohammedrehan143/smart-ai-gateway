"""Health and operational readiness endpoints."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from app.api.deps import get_repository
from app.api.schemas import HealthResponse
from app.core.config import settings
from app.domain.interfaces import TraceRepository

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_live():
    """Liveness probe - checks if the process is running."""
    return HealthResponse(
        status="live",
        timestamp=datetime.now(timezone.utc).isoformat(),
        gateway_version="0.1.0",
        environment=settings.APP_ENV,
    )


@router.get("/ready", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_ready(repo: TraceRepository = Depends(get_repository)):
    """Readiness probe - checks database connectivity without exposing secrets."""
    db_status = "connected"
    try:
        await repo.initialize()
    except Exception as e:
        db_status = f"unhealthy: {type(e).__name__}"

    return HealthResponse(
        status="ready" if db_status == "connected" else "degraded",
        timestamp=datetime.now(timezone.utc).isoformat(),
        gateway_version="0.1.0",
        database=db_status,
        environment=settings.APP_ENV,
    )
