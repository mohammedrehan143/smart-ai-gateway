"""Unit tests for retry logic and deadline calculation."""

from app.core.errors import (
    InvalidRequestError,
    ProviderAuthError,
    ProviderServerError,
    RateLimitError,
    RequestTimeoutError,
)
from app.domain.retry import DeadlineTracker, calculate_backoff, is_retryable_error


def test_retryable_error_classification():
    assert is_retryable_error(RateLimitError()) is True
    assert is_retryable_error(RequestTimeoutError()) is True
    assert is_retryable_error(ProviderServerError()) is True
    assert is_retryable_error(InvalidRequestError("bad payload")) is False
    assert is_retryable_error(ProviderAuthError("bad api key")) is False
    assert is_retryable_error(Exception("unhandled")) is False


def test_calculate_backoff():
    # Test retry-after override
    delay = calculate_backoff(attempt_number=1, retry_after_s=0.5)
    assert delay == 0.5

    # Test exponential growth
    d1 = calculate_backoff(attempt_number=1, jitter=False)
    d2 = calculate_backoff(attempt_number=2, jitter=False)
    assert d2 == d1 * 2


def test_deadline_tracker():
    tracker = DeadlineTracker(total_timeout_seconds=0.1)
    assert not tracker.is_expired
    assert tracker.remaining_seconds > 0.0
