"""Prometheus-compatible operational metrics collector."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple


class MetricsCollector:
    """Thread-safe, in-process Prometheus metrics tracker."""

    def __init__(self):
        self.request_counts: Dict[Tuple[str, str, str], int] = defaultdict(int)  # (policy, model, status)
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_estimated_cost_usd: float = 0.0
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.fallback_count: int = 0
        self.latencies_ms: List[int] = []

    def record_request(
        self,
        policy: str,
        model: str,
        status: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
        cached: bool = False,
        fallback_used: bool = False,
    ) -> None:
        key = (policy, model, status)
        self.request_counts[key] += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_estimated_cost_usd += cost_usd
        if cached:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
        if fallback_used:
            self.fallback_count += 1
        self.latencies_ms.append(latency_ms)
        if len(self.latencies_ms) > 1000:
            self.latencies_ms = self.latencies_ms[-1000:]

    def export_prometheus(self) -> str:
        """Render metrics in standard Prometheus text exposition format."""
        lines = [
            "# HELP gateway_requests_total Total number of chat completion requests processed",
            "# TYPE gateway_requests_total counter",
        ]
        for (policy, model, status), count in self.request_counts.items():
            lines.append(f'gateway_requests_total{{policy="{policy}",model="{model}",status="{status}"}} {count}')

        lines.extend(
            [
                "# HELP gateway_tokens_total Total tokens processed",
                "# TYPE gateway_tokens_total counter",
                f'gateway_tokens_total{{type="input"}} {self.total_input_tokens}',
                f'gateway_tokens_total{{type="output"}} {self.total_output_tokens}',
                "# HELP gateway_estimated_cost_usd Cumulative estimated spend in USD",
                "# TYPE gateway_estimated_cost_usd counter",
                f"gateway_estimated_cost_usd {self.total_estimated_cost_usd:.6f}",
                "# HELP gateway_cache_events_total Cache hit and miss events",
                "# TYPE gateway_cache_events_total counter",
                f'gateway_cache_events_total{{type="hit"}} {self.cache_hits}',
                f'gateway_cache_events_total{{type="miss"}} {self.cache_misses}',
                "# HELP gateway_fallbacks_total Total number of fallback model triggers",
                "# TYPE gateway_fallbacks_total counter",
                f"gateway_fallbacks_total {self.fallback_count}",
            ]
        )

        if self.latencies_ms:
            sorted_lat = sorted(self.latencies_ms)
            p50 = sorted_lat[int(len(sorted_lat) * 0.50)]
            p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
            lines.extend(
                [
                    "# HELP gateway_latency_ms Summary percentiles for request latency",
                    "# TYPE gateway_latency_ms gauge",
                    f'gateway_latency_ms{{quantile="0.50"}} {p50}',
                    f'gateway_latency_ms{{quantile="0.95"}} {p95}',
                ]
            )

        return "\n".join(lines) + "\n"


default_metrics = MetricsCollector()
