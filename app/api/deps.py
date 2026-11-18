"""FastAPI dependency providers with timing-attack resistant authentication, tenant isolation, and brute-force protection."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import List, Optional
from fastapi import Depends, Header, HTTPException, Request, status
from app.core.config import settings
from app.core.rate_limiter import default_rate_limiter
from app.domain.interfaces import TraceRepository
from app.providers.resolver import DynamicProviderAdapter
from app.repositories.sqlite import SqliteTraceRepository
from app.services.orchestrator import ChatOrchestrator

_repo_instance: Optional[TraceRepository] = None
_orchestrator_instance: Optional[ChatOrchestrator] = None


@dataclass
class AuthenticatedUser:
    """Authenticated identity derived from verified token."""

    user_id: str
    is_admin: bool = False
    tenant_id: str = "default"
    token_identifier: str = ""
    scopes: List[str] = field(default_factory=lambda: ["*"])


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


def _get_client_ip(request: Optional[Request]) -> str:
    if request and request.client:
        return request.client.host
    return "127.0.0.1"


async def get_authenticated_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
) -> AuthenticatedUser:
    """Derives user identity from verified authentication token with constant-time validation.

    Prevents unauthorized tenant impersonation and production bypasses.
    """
    client_ip = _get_client_ip(request)

    # 1. Check brute-force lockout
    is_locked, retry_after = default_rate_limiter.is_ip_locked_out(client_ip)
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
            detail={
                "error": {
                    "type": "rate_limited",
                    "message": f"IP temporarily locked out due to repeated failed authentication attempts. Retry in {retry_after} seconds.",
                    "retryable": False,
                }
            },
        )

    # 2. In dev/test mode with no GATEWAY_API_KEY set, permit local development
    if settings.is_dev_mode:
        resolved_user = x_user_id or "default_user"
        return AuthenticatedUser(
            user_id=resolved_user,
            is_admin=True,
            tenant_id=resolved_user,
            token_identifier="dev_local",
        )

    # 3. Production or key-configured mode: Authorization header is strictly mandatory
    if not authorization:
        default_rate_limiter.record_failed_auth(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "type": "unauthorized",
                    "message": "Missing Authorization header. Bearer token required.",
                    "retryable": False,
                }
            },
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        default_rate_limiter.record_failed_auth(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "type": "unauthorized",
                    "message": "Invalid authentication scheme. Expected 'Bearer <token>'.",
                    "retryable": False,
                }
            },
        )

    cleaned_token = token.strip()

    # 4. Check key revocation list
    for revoked_key in settings.REVOKED_API_KEYS:
        if revoked_key and secrets.compare_digest(cleaned_token, revoked_key.strip()):
            default_rate_limiter.record_failed_auth(client_ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "type": "unauthorized",
                        "message": "Authentication token has been revoked.",
                        "retryable": False,
                    }
                },
            )

    # 5. Check against tenant-specific token registry
    tenant_mappings = settings.get_tenant_key_mappings()
    for reg_key, mapped_user in tenant_mappings.items():
        if secrets.compare_digest(cleaned_token, reg_key):
            # Verified tenant token
            default_rate_limiter.reset_failed_auth(client_ip)
            # If client provided an X-User-ID header that differs from mapped tenant, reject impersonation!
            if x_user_id and x_user_id != mapped_user:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": {
                            "type": "forbidden",
                            "message": f"Tenant mismatch: Authenticated as '{mapped_user}' but requested X-User-ID '{x_user_id}'.",
                            "retryable": False,
                        }
                    },
                )
            auth_user = AuthenticatedUser(
                user_id=mapped_user,
                is_admin=False,
                tenant_id=mapped_user,
                token_identifier=f"tenant_{mapped_user}",
            )
            # Check tenant rate limit
            is_allowed, retry_after = default_rate_limiter.check_tenant_rate_limit(auth_user.tenant_id)
            if not is_allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers={"Retry-After": str(retry_after)},
                    detail={
                        "error": {
                            "type": "rate_limited",
                            "message": f"Tenant '{auth_user.tenant_id}' rate limit exceeded. Retry in {retry_after}s.",
                            "retryable": True,
                        }
                    },
                )
            return auth_user

    # 6. Check against master GATEWAY_API_KEY
    is_master_match = False
    if settings.GATEWAY_API_KEY and secrets.compare_digest(cleaned_token, settings.GATEWAY_API_KEY.strip()):
        is_master_match = True

    # 7. Check against ALLOWED_API_KEYS for key rotation
    if not is_master_match:
        for allowed_key in settings.ALLOWED_API_KEYS:
            if allowed_key and secrets.compare_digest(cleaned_token, allowed_key.strip()):
                is_master_match = True
                break

    if not is_master_match:
        default_rate_limiter.record_failed_auth(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "type": "unauthorized",
                    "message": "Invalid Bearer token.",
                    "retryable": False,
                }
            },
        )

    # Token is valid master/allowed admin key
    default_rate_limiter.reset_failed_auth(client_ip)
    effective_user = x_user_id or "default_user"
    auth_user = AuthenticatedUser(
        user_id=effective_user,
        is_admin=True,
        tenant_id=effective_user,
        token_identifier="master_key",
    )
    is_allowed, retry_after = default_rate_limiter.check_tenant_rate_limit(auth_user.tenant_id)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
            detail={
                "error": {
                    "type": "rate_limited",
                    "message": f"Tenant '{auth_user.tenant_id}' rate limit exceeded. Retry in {retry_after}s.",
                    "retryable": True,
                }
            },
        )
    return auth_user


async def verify_gateway_auth(
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> None:
    """Verifies authentication and populates authenticated user identity context."""
    # Depends(get_authenticated_user) handles complete validation
    return None
