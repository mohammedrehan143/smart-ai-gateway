"""OpenTelemetry-compatible request-level observability, structured spans, and distributed tracing."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger

logger = get_logger("observability")


@dataclass
class TraceEvent:
    name: str
    timestamp: float = field(default_factory=time.time)
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "attributes": self.attributes,
        }


@dataclass
class TraceSpan:
    trace_id: str
    span_id: str
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[TraceEvent] = field(default_factory=list)
    status: str = "OK"  # "OK", "ERROR"

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        self.events.append(TraceEvent(name=name, attributes=attributes or {}))

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def finish(self, status: str = "OK") -> None:
        self.end_time = time.time()
        self.status = status

    @property
    def duration_ms(self) -> int:
        end = self.end_time or time.time()
        return int((end - self.start_time) * 1000)

    def to_otel_dict(self) -> Dict[str, Any]:
        """Formats span matching OpenTelemetry standard JSON schema."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "name": self.name,
            "start_time_unix_nano": int(self.start_time * 1e9),
            "end_time_unix_nano": int((self.end_time or time.time()) * 1e9),
            "duration_ms": self.duration_ms,
            "status": {"code": self.status},
            "attributes": self.attributes,
            "events": [e.to_dict() for e in self.events],
        }


class ObservabilityTracer:
    """Creates and manages structured request spans and distributed telemetry."""

    @classmethod
    def start_span(
        cls,
        name: str,
        trace_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> TraceSpan:
        t_id = trace_id or f"tr_{int(time.time() * 1000):x}_{uuid.uuid4().hex[:12]}"
        s_id = f"sp_{uuid.uuid4().hex[:16]}"
        return TraceSpan(
            trace_id=t_id,
            span_id=s_id,
            name=name,
            attributes=attributes or {},
        )


default_tracer = ObservabilityTracer()
