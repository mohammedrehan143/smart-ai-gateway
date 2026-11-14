"""Base provider adapter definition."""

from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.entities import ChatMessage, GenerationParameters, NormalizedCompletion


class BaseProviderAdapter(ABC):
    """Abstract base class for provider adapters."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'mock', 'openai')."""
        pass

    @abstractmethod
    async def generate(
        self,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
        model_alias: str,
        timeout_seconds: float,
        tools: Optional[list] = None,
    ) -> NormalizedCompletion:
        """Send chat messages and return normalized completion."""
        pass
