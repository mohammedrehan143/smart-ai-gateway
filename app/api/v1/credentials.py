"""BYOK Encrypted Credential Management API endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import verify_gateway_auth
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


@router.post(
    "",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_gateway_auth)],
)
async def store_user_credential(
    payload: CredentialCreateInput,
    x_user_id: Optional[str] = Header("default_user", alias="X-User-ID"),
) -> Dict[str, Any]:
    """Securely stores an encrypted provider credential for a specific user."""
    cred = default_byok_manager.store_credential(
        user_id=x_user_id or "default_user",
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
    dependencies=[Depends(verify_gateway_auth)],
)
async def list_user_credentials(
    x_user_id: Optional[str] = Header("default_user", alias="X-User-ID"),
) -> List[Dict[str, Any]]:
    """Retrieves all registered provider credentials (masked) for the authenticated user."""
    return default_byok_manager.list_credentials(user_id=x_user_id or "default_user")


@router.delete(
    "/{provider}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
async def delete_user_credential(
    provider: str,
    x_user_id: Optional[str] = Header("default_user", alias="X-User-ID"),
) -> Dict[str, Any]:
    """Deletes/revokes a stored credential for a provider."""
    deleted = default_byok_manager.delete_credential(
        user_id=x_user_id or "default_user",
        provider=provider.lower(),
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No stored credential found for provider '{provider}'",
        )
    return {"status": "revoked", "provider": provider.lower()}
