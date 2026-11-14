"""FastAPI dependency providers with timing-attack resistant authentication."""

from __future__ import annotations

import secrets
from typing import Optional
from fastapi import Header, HTTPException, status
from app.core.config import settings
from app.domain.interfaces import TraceRepository
from app.providers.resolver import DynamicProviderAdapter
from app.repositories.sqlite import SqliteTraceRepository
from app.services.orchestrator import ChatOrchestrator

_repo_instance: Optional[TraceRepository] = None
_orchestrator_instance: Optional[ChatOrchestrator] = None


async def get_repository() -> TraceRepository:
    global _repo_instance
    if _repo_instance is None:
        _repo_instance = SqliteTraceRepository(settings.DATABASE_URL)
        await _repo_instance.initialize()
    return _repo_instance


async def get_orchestrator() -> ChatOrchestrator:
    global _orchestrator_instance
    if _orchestrator_instance is None:
        repo = await get_repository()
        adapter = DynamicProviderAdapter()
        _orchestrator_instance = ChatOrchestrator(repository=repo, default_adapter=adapter)
    return _orchestrator_instance


async def verify_gateway_auth(authorization: Optional[str] = Header(None)) -> None:
    """Verifies gateway bearer token using constant-time comparison."""
    if settings.is_dev_mode:
        return

    if not settings.GATEWAY_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"type": "server_misconfiguration", "message": "GATEWAY_API_KEY is not configured", "retryable": False}},
        )

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"type": "unauthorized", "message": "Missing Authorization header", "retryable": False}},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"type": "unauthorized", "message": "Invalid authentication scheme. Expected Bearer", "retryable": False}},
        )

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(token, settings.GATEWAY_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"type": "unauthorized", "message": "Invalid Bearer token", "retryable": False}},
        )
