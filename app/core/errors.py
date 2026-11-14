"""Error taxonomy and exception classes for Smart AI Gateway."""

from typing import Optional


class GatewayError(Exception):
    """Base exception for all gateway-managed errors."""

    def __init__(
        self,
        message: str,
        error_type: str = "internal_error",
        status_code: int = 500,
        retryable: bool = False,
        trace_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.status_code = status_code
        self.retryable = retryable
        self.trace_id = trace_id


class InvalidRequestError(GatewayError):
    def __init__(self, message: str, trace_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_type="invalid_request",
            status_code=400,
            retryable=False,
            trace_id=trace_id,
        )


class UnauthorizedError(GatewayError):
    def __init__(self, message: str = "Invalid or missing gateway credentials", trace_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_type="unauthorized",
            status_code=401,
            retryable=False,
            trace_id=trace_id,
        )


class RateLimitError(GatewayError):
    def __init__(self, message: str = "Rate limit exceeded", retry_after_s: Optional[float] = None, trace_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_type="rate_limited",
            status_code=429,
            retryable=True,
            trace_id=trace_id,
        )
        self.retry_after_s = retry_after_s


class RequestTimeoutError(GatewayError):
    def __init__(self, message: str = "Gateway deadline exceeded", trace_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_type="timeout",
            status_code=504,
            retryable=True,
            trace_id=trace_id,
        )


class ProviderServerError(GatewayError):
    def __init__(self, message: str = "Provider upstream error", trace_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_type="provider_server_error",
            status_code=502,
            retryable=True,
            trace_id=trace_id,
        )


class ProviderAuthError(GatewayError):
    def __init__(self, message: str = "Provider authentication configuration failed", trace_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_type="provider_auth_error",
            status_code=503,
            retryable=False,
            trace_id=trace_id,
        )


class ProviderUnavailableError(GatewayError):
    def __init__(self, message: str = "No configured model could complete the request", trace_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_type="provider_unavailable",
            status_code=503,
            retryable=False,
            trace_id=trace_id,
        )


class TelemetryDegradedError(GatewayError):
    def __init__(self, message: str = "Telemetry persistence degraded", trace_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_type="telemetry_degraded",
            status_code=200,
            retryable=False,
            trace_id=trace_id,
        )
