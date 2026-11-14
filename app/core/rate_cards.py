"""Versioned rate cards for model pricing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class RateCardEntry:
    rate_card_id: str
    model_alias: str
    provider: str
    input_rate_per_million: float
    output_rate_per_million: float
    currency: str = "USD"
    version: str = "2026-11-01"
    source_note: str = "Official published rates"


class RateCardCatalog:
    """Manages versioned model pricing rate cards."""

    def __init__(self, version: str = "2026-11-01"):
        self.version = version
        # Rates per 1M tokens in USD
        self._rates: Dict[str, RateCardEntry] = {
            "mock-cheap": RateCardEntry(
                rate_card_id=f"rc_mock_cheap_{version}",
                model_alias="mock-cheap",
                provider="mock",
                input_rate_per_million=0.15,
                output_rate_per_million=0.60,
                version=version,
            ),
            "mock-strong": RateCardEntry(
                rate_card_id=f"rc_mock_strong_{version}",
                model_alias="mock-strong",
                provider="mock",
                input_rate_per_million=2.50,
                output_rate_per_million=10.00,
                version=version,
            ),
            "gpt-4o-mini": RateCardEntry(
                rate_card_id=f"rc_gpt4omini_{version}",
                model_alias="gpt-4o-mini",
                provider="openai",
                input_rate_per_million=0.15,
                output_rate_per_million=0.60,
                version=version,
            ),
            "gpt-4o": RateCardEntry(
                rate_card_id=f"rc_gpt4o_{version}",
                model_alias="gpt-4o",
                provider="openai",
                input_rate_per_million=2.50,
                output_rate_per_million=10.00,
                version=version,
            ),
            "claude-3-5-sonnet": RateCardEntry(
                rate_card_id=f"rc_claude35sonnet_{version}",
                model_alias="claude-3-5-sonnet",
                provider="anthropic",
                input_rate_per_million=3.00,
                output_rate_per_million=15.00,
                version=version,
            ),
            "gemini-1.5-flash": RateCardEntry(
                rate_card_id=f"rc_gemini15flash_{version}",
                model_alias="gemini-1.5-flash",
                provider="google",
                input_rate_per_million=0.075,
                output_rate_per_million=0.30,
                version=version,
            ),
        }

    def get_rate(self, model_alias: str) -> Optional[RateCardEntry]:
        return self._rates.get(model_alias)

    def register_rate(self, entry: RateCardEntry) -> None:
        self._rates[entry.model_alias] = entry


default_rate_catalog = RateCardCatalog()
