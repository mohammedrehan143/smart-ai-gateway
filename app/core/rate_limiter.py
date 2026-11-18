"""Sliding-window rate limiter and brute-force authentication protection."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from app.core.config import settings


class InMemoryRateLimiter:
    """Thread-safe sliding window rate limiter and brute-force lockout manager."""

    def __init__(self):
        # Maps client_id -> list of timestamp floats
        self._request_windows: Dict[str, List[float]] = defaultdict(list)
        # Maps tenant_id -> list of timestamp floats
        self._tenant_windows: Dict[str, List[float]] = defaultdict(list)
        # Maps client_ip -> list of failed auth timestamp floats
        self._failed_auth_windows: Dict[str, List[float]] = defaultdict(list)
        # Maps client_ip -> lockout expiration timestamp float
        self._lockouts: Dict[str, float] = {}

    def _cleanup_old_entries(self, timestamps: List[float], cutoff: float) -> List[float]:
        return [ts for ts in timestamps if ts > cutoff]

    def check_rate_limit(self, client_id: str, limit_per_minute: Optional[int] = None) -> Tuple[bool, int]:
        """Checks if client exceeded rate limit.

        Returns:
            (is_allowed: bool, retry_after_seconds: int)
        """
        if not settings.RATE_LIMIT_ENABLED:
            return True, 0

        rpm = limit_per_minute or settings.RATE_LIMIT_RPM
        now = time.time()
        window_start = now - 60.0

        ts_list = self._cleanup_old_entries(self._request_windows[client_id], window_start)
        self._request_windows[client_id] = ts_list

        if len(ts_list) >= rpm:
            oldest = ts_list[0]
            retry_after = max(1, int(60.0 - (now - oldest)))
            return False, retry_after

        self._request_windows[client_id].append(now)
        return True, 0

    def check_tenant_rate_limit(self, tenant_id: str, limit_per_minute: Optional[int] = None) -> Tuple[bool, int]:
        """Checks if a tenant exceeded their request rate quota across all their connections."""
        if not settings.RATE_LIMIT_ENABLED:
            return True, 0

        rpm = limit_per_minute or (settings.RATE_LIMIT_RPM * 2)
        now = time.time()
        window_start = now - 60.0

        ts_list = self._cleanup_old_entries(self._tenant_windows[tenant_id], window_start)
        self._tenant_windows[tenant_id] = ts_list

        if len(ts_list) >= rpm:
            oldest = ts_list[0]
            retry_after = max(1, int(60.0 - (now - oldest)))
            return False, retry_after

        self._tenant_windows[tenant_id].append(now)
        return True, 0

    def record_failed_auth(self, client_ip: str) -> None:
        """Records a failed authentication attempt and locks out IP if threshold reached."""
        now = time.time()
        window_start = now - 300.0  # 5 minute window

        ts_list = self._cleanup_old_entries(self._failed_auth_windows[client_ip], window_start)
        ts_list.append(now)
        self._failed_auth_windows[client_ip] = ts_list

        if len(ts_list) >= settings.MAX_FAILED_AUTH_ATTEMPTS:
            # Lock out for 15 minutes (900s)
            self._lockouts[client_ip] = now + 900.0

    def is_ip_locked_out(self, client_ip: str) -> Tuple[bool, int]:
        """Checks if a client IP is currently locked out due to brute-force attempts."""
        now = time.time()
        lockout_expiry = self._lockouts.get(client_ip, 0.0)
        if lockout_expiry > now:
            retry_after = max(1, int(lockout_expiry - now))
            return True, retry_after
        elif lockout_expiry > 0.0:
            del self._lockouts[client_ip]
        return False, 0

    def reset_failed_auth(self, client_ip: str) -> None:
        """Clears failed authentication records upon successful login/verification."""
        if client_ip in self._failed_auth_windows:
            del self._failed_auth_windows[client_ip]
        if client_ip in self._lockouts:
            del self._lockouts[client_ip]

    def clear(self) -> None:
        """Resets all tracking windows, counters, and lockouts."""
        self._request_windows.clear()
        self._tenant_windows.clear()
        self._failed_auth_windows.clear()
        self._lockouts.clear()


default_rate_limiter = InMemoryRateLimiter()


def extract_client_ip(request: Optional[Any]) -> str:
    """Extracts true client IP, prioritizing reverse proxy headers (Cloudflare, Render, etc.)."""
    if not request:
        return "127.0.0.1"
    headers = getattr(request, "headers", {})
    # 1. Cloudflare connecting IP
    cf_ip = headers.get("cf-connecting-ip")
    if cf_ip and cf_ip.strip():
        return cf_ip.strip()
    # 2. X-Forwarded-For (client is the first IP in the chain)
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[0]
    # 3. X-Real-IP
    real_ip = headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    # 4. Fallback to direct client host
    client = getattr(request, "client", None)
    if client and getattr(client, "host", None):
        return client.host
    return "127.0.0.1"
