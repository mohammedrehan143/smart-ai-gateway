"""Retry and fallback policy logic."""

from __future__ import annotations

import random
import time
from typing import Optional
from app.core.errors import GatewayError


def is_retryable_error(error: Exception) -> bool:
    """Determine if an exception is transient and safe to retry."""
    if isinstance(error, GatewayError):
        return error.retryable
    return False


def calculate_backoff(
    attempt_number: int,
    base_delay_s: float = 0.05,
    max_delay_s: float = 1.0,
    jitter: bool = True,
    retry_after_s: Optional[float] = None,
) -> float:
    """Calculate exponential backoff with optional jitter and Retry-After header respect."""
    if retry_after_s is not None and retry_after_s > 0:
        return min(retry_after_s, max_delay_s)

    delay = base_delay_s * (2 ** (attempt_number - 1))
    delay = min(delay, max_delay_s)
    if jitter:
        delay = delay * (0.5 + random.random() * 0.5)
    return delay


class DeadlineTracker:
    """Tracks deadline budget remaining across retries and fallbacks."""

    def __init__(self, total_timeout_seconds: float):
        self.total_timeout = total_timeout_seconds
        self.start_time = time.time()

    @property
    def remaining_seconds(self) -> float:
        elapsed = time.time() - self.start_time
        return max(0.0, self.total_timeout - elapsed)

    @property
    def is_expired(self) -> bool:
        return self.remaining_seconds <= 0.001
