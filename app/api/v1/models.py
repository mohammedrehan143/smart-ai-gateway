"""Models catalog and capabilities endpoint."""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status
from app.api.deps import verify_gateway_auth
from app.core.rate_cards import default_rate_catalog
from app.domain.registry import registry

router = APIRouter(prefix="/v1", tags=["Models"])


@router.get(
    "/models",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
async def list_models() -> Dict[str, Any]:
    """Lists allowlisted models, provider metadata, capabilities, and pricing rate cards."""
    models_data: List[Dict[str, Any]] = []

    for model in registry.list_models():
        rate_entry = default_rate_catalog.get_rate(model.alias)
        pricing = {
            "input_rate_per_million": rate_entry.input_rate_per_million if rate_entry else 0.0,
            "output_rate_per_million": rate_entry.output_rate_per_million if rate_entry else 0.0,
            "currency": rate_entry.currency if rate_entry else "USD",
            "rate_card_version": rate_entry.version if rate_entry else "default",
        }

        models_data.append(
            {
                "id": model.alias,
                "alias": model.alias,
                "provider": model.provider,
                "upstream_model_id": model.upstream_model_id,
                "tier": model.tier,
                "context_window": model.context_window,
                "max_output_tokens": model.max_output_tokens,
                "supports_tools": model.supports_tools,
                "supports_json": model.supports_json,
                "is_active": model.is_active,
                "version": model.version,
                "pricing": pricing,
            }
        )

    return {
        "object": "list",
        "data": models_data,
        "total": len(models_data),
    }
