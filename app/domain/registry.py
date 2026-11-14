"""Model registry and configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional


@dataclass
class ModelMetadata:
    alias: str
    provider: str
    upstream_model_id: str
    tier: Literal["cheap", "strong"]
    context_window: int
    max_output_tokens: int
    supports_tools: bool = True
    supports_json: bool = True
    is_active: bool = True
    version: str = "1.0.0"


class ModelRegistry:
    """Registry of allowlisted models and configurations."""

    def __init__(self):
        self._models: Dict[str, ModelMetadata] = {
            "mock-cheap": ModelMetadata(
                alias="mock-cheap",
                provider="mock",
                upstream_model_id="mock-cheap-v1",
                tier="cheap",
                context_window=16384,
                max_output_tokens=4096,
            ),
            "mock-strong": ModelMetadata(
                alias="mock-strong",
                provider="mock",
                upstream_model_id="mock-strong-v1",
                tier="strong",
                context_window=128000,
                max_output_tokens=8192,
            ),
            "gpt-4o-mini": ModelMetadata(
                alias="gpt-4o-mini",
                provider="openai",
                upstream_model_id="gpt-4o-mini",
                tier="cheap",
                context_window=128000,
                max_output_tokens=16384,
            ),
            "gpt-4o": ModelMetadata(
                alias="gpt-4o",
                provider="openai",
                upstream_model_id="gpt-4o",
                tier="strong",
                context_window=128000,
                max_output_tokens=16384,
            ),
        }

    def get_model(self, alias: str) -> Optional[ModelMetadata]:
        return self._models.get(alias)

    def register(self, model: ModelMetadata) -> None:
        self._models[model.alias] = model

    def list_models(self) -> List[ModelMetadata]:
        return list(self._models.values())

    def get_by_tier(self, tier: Literal["cheap", "strong"], provider: Optional[str] = None) -> List[ModelMetadata]:
        return [
            m for m in self._models.values()
            if m.tier == tier and (provider is None or m.provider == provider) and m.is_active
        ]


registry = ModelRegistry()
