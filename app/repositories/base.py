"""Base repository interfaces."""

from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.entities import (
    GatewayRequestRecord,
    ProviderAttemptRecord,
    RoutingDecision,
    UsageRecord,
)


class BaseTraceRepository(ABC):
    """Abstract interface for storing and retrieving gateway traces."""

    @abstractmethod
    async def initialize(self) -> None:
        """Create tables and indexes if they do not exist."""
        pass

    @abstractmethod
    async def record_request(self, record: GatewayRequestRecord) -> None:
        pass

    @abstractmethod
    async def record_attempt(self, record: ProviderAttemptRecord) -> None:
        pass

    @abstractmethod
    async def record_decision(self, record: RoutingDecision, gateway_request_id: str) -> None:
        pass

    @abstractmethod
    async def record_usage(self, record: UsageRecord) -> None:
        pass

    @abstractmethod
    async def get_request_by_trace_id(self, trace_id: str) -> Optional[GatewayRequestRecord]:
        pass

    @abstractmethod
    async def get_attempts(self, gateway_request_id: str) -> List[ProviderAttemptRecord]:
        pass

    @abstractmethod
    async def get_usage(self, gateway_request_id: str) -> Optional[UsageRecord]:
        pass

    async def get_usage_summary(self, since_timestamp: Optional[float] = None, limit: int = 100) -> dict:
        return {}

    async def get_cost_summary(self, since_timestamp: Optional[float] = None) -> dict:
        return {}

    async def get_recent_decisions(self, limit: int = 20) -> list:
        return []

    async def get_recent_requests(self, limit: int = 50, since_timestamp: Optional[float] = None) -> list:
        return []

