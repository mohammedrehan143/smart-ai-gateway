"""Deterministic Mock Provider Adapter for testing and foundation pipeline."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional
from app.core.errors import (
    ProviderAuthError,
    ProviderServerError,
    RateLimitError,
    RequestTimeoutError,
)
from app.domain.entities import ChatMessage, GenerationParameters, NormalizedCompletion
from app.providers.base import BaseProviderAdapter


class MockProviderAdapter(BaseProviderAdapter):
    """Deterministic mock provider that simulates completions and failures."""

    def __init__(self, failure_mode: Optional[str] = None, latency_delay_s: float = 0.0):
        self.failure_mode = failure_mode  # e.g., 'timeout', '500', '429', '401'
        self.latency_delay_s = latency_delay_s
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate(
        self,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
        model_alias: str,
        timeout_seconds: float,
        tools: Optional[list] = None,
    ) -> NormalizedCompletion:
        self.call_count += 1

        if self.latency_delay_s > 0:
            await asyncio.sleep(self.latency_delay_s)

        if self.failure_mode == "timeout":
            raise RequestTimeoutError("Mock provider simulated timeout")
        elif self.failure_mode == "500":
            raise ProviderServerError("Mock provider simulated 500 server error")
        elif self.failure_mode == "429":
            raise RateLimitError("Mock provider simulated 429 rate limit", retry_after_s=0.1)
        elif self.failure_mode == "401":
            raise ProviderAuthError("Mock provider simulated 401 unauthorized")

        last_user_message = ""
        for m in reversed(messages):
            if m.role == "user":
                last_user_message = m.content
                break

        # Check if user message triggers deterministic tool calls in evaluation
        tool_calls: Optional[List[Dict[str, Any]]] = None
        if tools and "calculate" in last_user_message.lower():
            tool_calls = [
                {
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {"name": "calculator", "arguments": "{\"expression\": \"2 + 2\"}"},
                }
            ]
            content = ""
            finish_reason = "tool_calls"
        else:
            content = f"Mock completion response for: {last_user_message}"
            finish_reason = "stop"

        input_text = " ".join(m.content for m in messages)
        input_tokens = max(1, len(input_text.split()))
        output_tokens = max(1, len(content.split())) if content else 10

        return NormalizedCompletion(
            content=content,
            finish_reason=finish_reason,
            provider=self.provider_name,
            model_alias=model_alias,
            provider_request_id=f"mock_req_{uuid.uuid4().hex[:10]}",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            raw_usage_available=True,
            tool_calls=tool_calls,
        )
