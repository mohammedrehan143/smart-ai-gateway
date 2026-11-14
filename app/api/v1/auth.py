"""Authentication and token verification endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from app.api.deps import verify_gateway_auth
from app.core.config import settings

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


@router.get(
    "/verify",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
async def verify_credentials() -> dict:
    """Verifies gateway authentication credentials and returns session metadata."""
    return {
        "status": "authenticated",
        "auth_enforced": bool(settings.GATEWAY_API_KEY and not settings.is_dev_mode),
        "gateway_version": "0.1.0",
        "environment": settings.APP_ENV,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "routing_policy_version": settings.ROUTING_POLICY_VERSION,
        "rate_card_version": settings.RATE_CARD_VERSION,
    }
