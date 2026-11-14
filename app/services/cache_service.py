"""In-memory response cache implementation with TTL and metrics."""

from __future__ import annotations

import time
from typing import Dict, NamedTuple, Optional
from app.core.logging import get_logger
from app.domain.entities import NormalizedCompletion
from app.domain.interfaces import CacheService

logger = get_logger("cache")


class CacheEntry(NamedTuple):
    completion: NormalizedCompletion
    expires_at: float


class InMemoryCacheService(CacheService):
    """In-memory response cache with TTL expiration."""

    def __init__(self, default_ttl_seconds: int = 300):
        self.default_ttl = default_ttl_seconds
        self._store: Dict[str, CacheEntry] = {}
        self.hits: int = 0
        self.misses: int = 0

    async def get(self, cache_key: str) -> Optional[NormalizedCompletion]:
        entry = self._store.get(cache_key)
        if not entry:
            self.misses += 1
            return None

        if time.time() > entry.expires_at:
            del self._store[cache_key]
            self.misses += 1
            return None

        self.hits += 1
        return entry.completion

    async def set(
        self,
        cache_key: str,
        completion: NormalizedCompletion,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        expires_at = time.time() + ttl
        self._store[cache_key] = CacheEntry(completion=completion, expires_at=expires_at)

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0


default_cache_service = InMemoryCacheService()
