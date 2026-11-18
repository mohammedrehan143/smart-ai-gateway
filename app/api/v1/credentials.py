"""BYOK Encrypted Credential Management API endpoints with strict tenant isolation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import AuthenticatedUser, get_authenticated_user
from app.domain.byok import default_byok_manager

router = APIRouter(prefix="/v1/credentials", tags=["Credentials"])


class CredentialCreateInput(BaseModel):
    provider: str = Field(..., description="Provider name: openai, anthropic, google, groq")
    api_key: str = Field(..., min_length=5, description="Provider API Key to encrypt and store")
    base_url: Optional[str] = Field(None, description="Optional custom provider endpoint base URL")


class CredentialResponse(BaseModel):
    provider: str
    masked_key: str
    base_url: Optional[str]
    is_active: bool
    created_at: float
    updated_at: float


def _resolve_effective_user(user: AuthenticatedUser, x_user_id: Optional[str]) -> str:
    """Enforces that only admin tokens may act on behalf of another user_id."""
    if user.is_admin and x_user_id:
        return x_user_id
    return user.user_id


@router.post(
    "",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def store_user_credential(
    payload: CredentialCreateInput,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
) -> Dict[str, Any]:
    """Securely stores an encrypted provider credential for the authenticated user."""
    effective_user = _resolve_effective_user(user, x_user_id)
    cred = default_byok_manager.store_credential(
        user_id=effective_user,
        provider=payload.provider.lower(),
        api_key=payload.api_key,
        base_url=payload.base_url,
    )
    return {
        "provider": cred.provider,
        "masked_key": cred.masked_key,
        "base_url": cred.base_url,
        "is_active": cred.is_active,
        "created_at": cred.created_at,
        "updated_at": cred.updated_at,
    }


@router.get(
    "",
    response_model=List[CredentialResponse],
    status_code=status.HTTP_200_OK,
)
async def list_user_credentials(
    user: AuthenticatedUser = Depends(get_authenticated_user),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
) -> List[Dict[str, Any]]:
    """Retrieves all registered provider credentials (masked) strictly for the authenticated user."""
    effective_user = _resolve_effective_user(user, x_user_id)
    return default_byok_manager.list_credentials(user_id=effective_user)


@router.delete(
    "/{provider}",
    status_code=status.HTTP_200_OK,
)
async def delete_user_credential(
    provider: str,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
) -> Dict[str, Any]:
    """Deletes/revokes a stored credential for a provider for the authenticated user."""
    effective_user = _resolve_effective_user(user, x_user_id)
    deleted = default_byok_manager.delete_credential(
        user_id=effective_user,
        provider=provider.lower(),
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No stored credential found for provider '{provider}'",
        )
    return {"status": "revoked", "provider": provider.lower()}
