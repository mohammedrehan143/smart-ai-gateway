"""Per-model and per-provider Circuit Breaker pattern implementation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal execution; upstream is healthy
    OPEN = "OPEN"            # Tripped; traffic immediately blocked to prevent cascade
    HALF_OPEN = "HALF_OPEN"  # Testing recovery with bounded test request


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3       # Trip to OPEN after 3 consecutive failures
    cooldown_seconds: float = 30.0   # Wait 30s before trying HALF_OPEN recovery
    half_open_trials: int = 1        # Number of successes needed to close circuit


class CircuitBreaker:
    """Stateful circuit breaker protecting against upstream provider failure storms."""

    def __init__(self, key: str, config: Optional[CircuitBreakerConfig] = None):
        self.key = key
        self.config = config or CircuitBreakerConfig()
        self.state: CircuitState = CircuitState.CLOSED
        self.consecutive_failures: int = 0
        self.total_failures: int = 0
        self.total_successes: int = 0
        self.last_failure_time: float = 0.0
        self.last_state_change: float = time.time()
        self.half_open_success_count: int = 0

    def is_available(self) -> bool:
        """Determines if requests are permitted through this circuit breaker."""
        now = time.time()
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if cooldown period elapsed to attempt recovery
            if now - self.last_state_change >= self.config.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
                self.half_open_success_count = 0
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Permit bounded probe trial
            return True

        return True

    def record_success(self) -> None:
        """Records a successful execution and transitions state if in recovery."""
        self.total_successes += 1
        now = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.half_open_success_count += 1
            if self.half_open_success_count >= self.config.half_open_trials:
                self.state = CircuitState.CLOSED
                self.consecutive_failures = 0
                self.last_state_change = now
        elif self.state == CircuitState.CLOSED:
            self.consecutive_failures = 0

    def record_failure(self, error: Optional[Exception] = None) -> None:
        """Records an execution failure and trips circuit if threshold exceeded."""
        self.total_failures += 1
        self.consecutive_failures += 1
        now = time.time()
        self.last_failure_time = now

        if self.state == CircuitState.HALF_OPEN:
            # Immediate re-trip on failure during probe
            self.state = CircuitState.OPEN
            self.last_state_change = now
        elif self.state == CircuitState.CLOSED:
            if self.consecutive_failures >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
                self.last_state_change = now

    def reset(self) -> None:
        """Manually resets circuit breaker back to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.last_state_change = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "is_available": self.is_available(),
        }


class CircuitBreakerRegistry:
    """Registry maintaining circuit breakers for models and providers."""

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}

    def get_breaker(self, model_alias: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        if model_alias not in self._breakers:
            self._breakers[model_alias] = CircuitBreaker(key=model_alias, config=config)
        return self._breakers[model_alias]

    def is_model_healthy(self, model_alias: str) -> bool:
        breaker = self.get_breaker(model_alias)
        return breaker.is_available()

    def record_outcome(self, model_alias: str, success: bool, error: Optional[Exception] = None) -> None:
        breaker = self.get_breaker(model_alias)
        if success:
            breaker.record_success()
        else:
            breaker.record_failure(error)

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        return {alias: b.to_dict() for alias, b in self._breakers.items()}

    def reset_all(self) -> None:
        for b in self._breakers.values():
            b.reset()


default_circuit_registry = CircuitBreakerRegistry()
