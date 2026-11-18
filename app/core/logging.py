"""Structured JSON logging with correlation IDs and redaction."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

correlation_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_trace_id", default="")
correlation_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_request_id", default="")

SENSITIVE_KEYS = {"authorization", "api_key", "password", "secret", "token", "gateway_api_key", "provider_api_key"}


def redact_data(data: Any) -> Any:
    """Recursively redact sensitive keys from dictionaries or structures."""
    if isinstance(data, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in data.items():
            if any(s in k.lower() for s in SENSITIVE_KEYS):
                cleaned[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                cleaned[k] = redact_data(v)
            else:
                cleaned[k] = v
        return cleaned
    elif isinstance(data, list):
        return [redact_data(item) for item in data]
    return data


class JsonFormatter(logging.Formatter):
    """Formats log records as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        from app.core.crypto import redact_secrets_from_text

        raw_message = record.getMessage()
        sanitized_message = redact_secrets_from_text(raw_message)

        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitized_message,
            "trace_id": correlation_trace_id.get(""),
            "request_id": correlation_request_id.get(""),
        }

        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_obj["data"] = redact_data(record.extra_data)

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def configure_logging(level_name: str = "INFO") -> None:
    """Configures application root logging with JSON output."""
    root = logging.getLogger()
    root.setLevel(level_name.upper())

    # Remove existing handlers
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
