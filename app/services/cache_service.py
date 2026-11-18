"""In-memory response cache implementation with TTL and LRU eviction metrics."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import NamedTuple, Optional
from app.core.logging import get_logger
from app.domain.entities import NormalizedCompletion
from app.domain.interfaces import CacheService

logger = get_logger("cache")


class CacheEntry(NamedTuple):
    completion: NormalizedCompletion
    expires_at: float


class InMemoryCacheService(CacheService):
    """In-memory response cache with TTL expiration and bounded LRU capacity."""

    def __init__(self, default_ttl_seconds: int = 300, max_entries: int = 5000):
        self.default_ttl = default_ttl_seconds
        self.max_entries = max_entries
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self.hits: int = 0
        self.misses: int = 0

    async def get(self, cache_key: str) -> Optional[NormalizedCompletion]:
        entry = self._store.get(cache_key)
        if not entry:
            self.misses += 1
            return None

        if time.time() > entry.expires_at:
            self._store.pop(cache_key, None)
            self.misses += 1
            return None

        # Move to end for LRU touch
        self._store.move_to_end(cache_key)
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

        # If key already exists, overwrite and move to end
        if cache_key in self._store:
            self._store[cache_key] = CacheEntry(completion=completion, expires_at=expires_at)
            self._store.move_to_end(cache_key)
            return

        # Enforce LRU cap: prune expired entries first if capacity reached
        if len(self._store) >= self.max_entries:
            now = time.time()
            expired_keys = [k for k, v in self._store.items() if now > v.expires_at]
            for k in expired_keys:
                self._store.pop(k, None)

            # If still at cap, evict oldest entry
            while len(self._store) >= self.max_entries:
                self._store.popitem(last=False)

        self._store[cache_key] = CacheEntry(completion=completion, expires_at=expires_at)

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0


default_cache_service = InMemoryCacheService()
