"""Protocols and abstract interfaces for domain boundaries."""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable
from app.domain.entities import (
    ChatMessage,
    GatewayRequestRecord,
    GenerationParameters,
    NormalizedCompletion,
    ProviderAttemptRecord,
    RoutingDecision,
    UsageRecord,
)


@runtime_checkable
class ProviderAdapter(Protocol):
    """Protocol for upstream provider implementations."""

    async def generate(
        self,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
        model_alias: str,
        timeout_seconds: float,
        tools: Optional[list] = None,
    ) -> NormalizedCompletion: ...


@runtime_checkable
class TraceRepository(Protocol):
    """Protocol for telemetry and trace persistence."""

    async def record_request(self, record: GatewayRequestRecord) -> None: ...

    async def record_attempt(self, record: ProviderAttemptRecord) -> None: ...

    async def record_decision(self, record: RoutingDecision, gateway_request_id: str) -> None: ...

    async def record_usage(self, record: UsageRecord) -> None: ...

    async def get_request(self, request_id: str) -> Optional[GatewayRequestRecord]: ...

    async def get_request_by_trace_id(self, trace_id: str) -> Optional[GatewayRequestRecord]: ...

    async def get_attempts(self, gateway_request_id: str) -> List[ProviderAttemptRecord]: ...


@runtime_checkable
class CacheService(Protocol):
    """Protocol for response caching."""

    async def get(self, cache_key: str) -> Optional[NormalizedCompletion]: ...

    async def set(self, cache_key: str, completion: NormalizedCompletion, ttl_seconds: int) -> None: ...
