"""Cost calculation engine according to docs/18_COST_MODEL.md."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional
from app.core.rate_cards import RateCardCatalog, default_rate_catalog


@dataclass
class CostCalculationResult:
    estimated_cost: Optional[float]
    currency: str
    cost_status: Literal["calculated", "estimated", "unavailable"]
    rate_card_id: Optional[str]
    input_rate: Optional[float]
    output_rate: Optional[float]


class CostCalculator:
    """Calculates request costs based on versioned rate cards."""

    def __init__(self, catalog: Optional[RateCardCatalog] = None):
        self.catalog = catalog or default_rate_catalog

    def calculate(
        self,
        model_alias: str,
        input_tokens: int,
        output_tokens: int,
        is_provider_usage: bool = True,
    ) -> CostCalculationResult:
        rate = self.catalog.get_rate(model_alias)
        if not rate:
            return CostCalculationResult(
                estimated_cost=None,
                currency="USD",
                cost_status="unavailable",
                rate_card_id=None,
                input_rate=None,
                output_rate=None,
            )

        cost = (input_tokens * rate.input_rate_per_million + output_tokens * rate.output_rate_per_million) / 1_000_000.0

        status: Literal["calculated", "estimated"] = "calculated" if is_provider_usage else "estimated"

        return CostCalculationResult(
            estimated_cost=round(cost, 6),
            currency=rate.currency,
            cost_status=status,
            rate_card_id=rate.rate_card_id,
            input_rate=rate.input_rate_per_million,
            output_rate=rate.output_rate_per_million,
        )


default_cost_calculator = CostCalculator()
