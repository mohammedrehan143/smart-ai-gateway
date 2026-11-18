"""Budget and Cost Optimization API endpoints with tenant isolation."""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field

from app.api.deps import AuthenticatedUser, get_authenticated_user
from app.domain.budget import default_budget_controller

router = APIRouter(prefix="/v1/budgets", tags=["Budgets"])


class BudgetUpdateRequest(BaseModel):
    project_id: str = Field(default="default_project", description="Project or workspace identifier")
    max_cost_per_request: Optional[float] = Field(None, ge=0.0, description="Maximum allowed cost per single request ($)")
    daily_budget: Optional[float] = Field(None, ge=0.0, description="Daily spend cap in USD")
    monthly_budget: Optional[float] = Field(None, ge=0.0, description="Monthly spend cap in USD")


def _resolve_effective_user(user: AuthenticatedUser, x_user_id: Optional[str]) -> str:
    if user.is_admin and x_user_id:
        return x_user_id
    return user.user_id


@router.post(
    "",
    status_code=status.HTTP_200_OK,
)
async def set_project_budget(
    payload: BudgetUpdateRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
) -> Dict[str, Any]:
    """Sets or updates budget limits for a given user and project."""
    effective_user = _resolve_effective_user(user, x_user_id)
    limit = default_budget_controller.set_budget(
        user_id=effective_user,
        project_id=payload.project_id,
        max_cost_per_request=payload.max_cost_per_request,
        daily_budget=payload.daily_budget,
        monthly_budget=payload.monthly_budget,
    )
    summary = default_budget_controller.get_spend_summary(user_id=effective_user, project_id=payload.project_id)
    return {
        "status": "configured",
        "budget": {
            "user_id": limit.user_id,
            "project_id": limit.project_id,
            "max_cost_per_request": limit.max_cost_per_request,
            "daily_budget": limit.daily_budget,
            "monthly_budget": limit.monthly_budget,
        },
        "spend_summary": summary,
    }


@router.get(
    "/{project_id}",
    status_code=status.HTTP_200_OK,
)
async def get_project_budget(
    project_id: str,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
) -> Dict[str, Any]:
    """Retrieves current budget settings and tracked spend for a project."""
    effective_user = _resolve_effective_user(user, x_user_id)
    summary = default_budget_controller.get_spend_summary(user_id=effective_user, project_id=project_id)
    return summary
