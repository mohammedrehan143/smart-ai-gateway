"""Proactive budget optimization, per-request caps, and tenant spend tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


@dataclass
class BudgetLimit:
    user_id: str
    project_id: str
    max_cost_per_request: Optional[float] = None  # e.g., $0.05
    daily_budget: Optional[float] = None  # e.g., $10.00
    monthly_budget: Optional[float] = None  # e.g., $200.00


class BudgetController:
    """Enforces pre-execution financial limits and tracks tenant spend."""

    def __init__(self):
        # Limits: Dict[(user_id, project_id), BudgetLimit]
        self._limits: Dict[Tuple[str, str], BudgetLimit] = {}
        # Spend tracking: Dict[(user_id, project_id, date_str), float]
        self._daily_spend: Dict[Tuple[str, str, str], float] = {}
        self._monthly_spend: Dict[Tuple[str, str, str], float] = {}

    def set_budget(
        self,
        user_id: str,
        project_id: str,
        max_cost_per_request: Optional[float] = None,
        daily_budget: Optional[float] = None,
        monthly_budget: Optional[float] = None,
    ) -> BudgetLimit:
        key = (user_id, project_id)
        limit = BudgetLimit(
            user_id=user_id,
            project_id=project_id,
            max_cost_per_request=max_cost_per_request,
            daily_budget=daily_budget,
            monthly_budget=monthly_budget,
        )
        self._limits[key] = limit
        return limit

    def get_budget(self, user_id: str, project_id: str) -> Optional[BudgetLimit]:
        return self._limits.get((user_id, project_id))

    def _get_date_keys(self) -> Tuple[str, str]:
        now = datetime.now(timezone.utc)
        day_key = now.strftime("%Y-%m-%d")
        month_key = now.strftime("%Y-%m")
        return day_key, month_key

    def check_budget_available(
        self,
        user_id: str,
        project_id: str,
        estimated_cost: float,
        request_cost_limit: Optional[float] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Validates if execution is within configured financial budgets prior to upstream dispatch."""
        key = (user_id, project_id)
        limit = self._limits.get(key)
        day_key, month_key = self._get_date_keys()

        # 1. Per-request cost cap check (either caller-supplied or project config)
        max_cost = request_cost_limit or (limit.max_cost_per_request if limit else None)
        if max_cost is not None and estimated_cost > max_cost:
            return False, f"Estimated request cost (${estimated_cost:.6f}) exceeds per-request limit (${max_cost:.6f})"

        if not limit:
            return True, None

        # 2. Daily budget check
        current_daily = self._daily_spend.get((user_id, project_id, day_key), 0.0)
        if limit.daily_budget is not None and (current_daily + estimated_cost) > limit.daily_budget:
            return (
                False,
                f"Daily project budget exceeded: current ${current_daily:.4f} + est ${estimated_cost:.4f} > limit ${limit.daily_budget:.4f}",
            )

        # 3. Monthly budget check
        current_monthly = self._monthly_spend.get((user_id, project_id, month_key), 0.0)
        if limit.monthly_budget is not None and (current_monthly + estimated_cost) > limit.monthly_budget:
            return (
                False,
                f"Monthly project budget exceeded: current ${current_monthly:.4f} + est ${estimated_cost:.4f} > limit ${limit.monthly_budget:.4f}",
            )

        return True, None

    def record_spend(self, user_id: str, project_id: str, actual_cost: float) -> None:
        """Records reconciled actual provider billed spend."""
        day_key, month_key = self._get_date_keys()
        day_tuple = (user_id, project_id, day_key)
        month_tuple = (user_id, project_id, month_key)

        self._daily_spend[day_tuple] = self._daily_spend.get(day_tuple, 0.0) + actual_cost
        self._monthly_spend[month_tuple] = self._monthly_spend.get(month_tuple, 0.0) + actual_cost

    def get_spend_summary(self, user_id: str, project_id: str) -> Dict[str, Any]:
        day_key, month_key = self._get_date_keys()
        limit = self._limits.get((user_id, project_id))

        return {
            "user_id": user_id,
            "project_id": project_id,
            "today_spend": round(self._daily_spend.get((user_id, project_id, day_key), 0.0), 6),
            "month_spend": round(self._monthly_spend.get((user_id, project_id, month_key), 0.0), 6),
            "daily_budget": limit.daily_budget if limit else None,
            "monthly_budget": limit.monthly_budget if limit else None,
            "max_cost_per_request": limit.max_cost_per_request if limit else None,
        }

    def clear(self) -> None:
        self._limits.clear()
        self._daily_spend.clear()
        self._monthly_spend.clear()


default_budget_controller = BudgetController()
