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
                    "function": {"name": "calculator", "arguments": '{"expression": "2 + 2"}'},
                }
            ]
            content = ""
            finish_reason = "tool_calls"
        else:
            lower_msg = last_user_message.lower().strip()
            tokens_set = set(lower_msg.replace("?", " ").replace("!", " ").replace(".", " ").split())
            if any(g in tokens_set for g in ("hi", "hello", "hey", "hy", "greetings", "yo", "sup")):
                content = "Mock completion response: Hello! I am the Smart AI Gateway Assistant. How can I help you today with coding, architecture, or model routing?"
            elif any(w in lower_msg for w in ("who are you", "what are you", "what is your name", "your name?")):
                content = "Mock completion response: I am the Smart AI Gateway Assistant, an intelligent multi-agent routing and execution platform designed to orchestrate Weak and Strong AI models seamlessly."
            elif any(w in lower_msg for w in ("website", "landing page", "web page", "create a site", "build a site", "html site")):
                content = (
                    "Mock completion response: Here is a complete, modern responsive website.\n\n"
                    "```action:write_file\n"
                    "{\n"
                    '  "path": "index.html",\n'
                    '  "content": "<!DOCTYPE html>\\n<html lang=\\"en\\">\\n<head>\\n    <meta charset=\\"UTF-8\\">\\n    <meta name=\\"viewport\\" content=\\"width=device-width, initial-scale=1.0\\">\\n    <title>Modern Website</title>\\n    <style>\\n        * { box-sizing: border-box; margin: 0; padding: 0; }\\n        body { font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; text-align: center; }\\n        .card { max-width: 600px; margin: 4rem auto; padding: 2.5rem; background: #1e293b; border-radius: 12px; border: 1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }\\n        h1 { color: #818cf8; margin-bottom: 1rem; font-size: 2rem; }\\n        p { color: #94a3b8; line-height: 1.6; font-size: 1.1rem; }\\n    </style>\\n</head>\\n<body>\\n    <div class=\\"card\\">\\n        <h1>Welcome to Your Website</h1>\\n        <p>This website was generated directly by the Smart AI Gateway.</p>\\n    </div>\\n</body>\\n</html>"\n'
                    "}\n"
                    "```"
                )
            elif "login" in lower_msg:
                content = (
                    "Mock completion response: Here is a complete login page.\n\n"
                    "```action:write_file\n"
                    "{\n"
                    '  "path": "login.html",\n'
                    '  "content": "<!DOCTYPE html>\\n<html lang=\\"en\\">\\n<head>\\n    <meta charset=\\"UTF-8\\">\\n    <title>Login</title>\\n    <style>\\n        body { font-family: Arial, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; background: #f1f5f9; margin: 0; }\\n        .box { background: #fff; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: 320px; }\\n        h2 { text-align: center; margin-bottom: 1.5rem; }\\n        input { width: 100%; padding: 0.6rem; margin-bottom: 1rem; border: 1px solid #cbd5e1; border-radius: 4px; box-sizing: border-box; }\\n        button { width: 100%; padding: 0.75rem; background: #4f46e5; color: #fff; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; }\\n    </style>\\n</head>\\n<body>\\n    <div class=\\"box\\">\\n        <h2>Sign In</h2>\\n        <form action=\\"/login\\" method=\\"POST\\">\\n            <input type=\\"text\\" name=\\"username\\" placeholder=\\"Username\\" required>\\n            <input type=\\"password\\" name=\\"password\\" placeholder=\\"Password\\" required>\\n            <button type=\\"submit\\">Log In</button>\\n        </form>\\n    </div>\\n</body>\\n</html>"\n'
                    "}\n"
                    "```"
                )
            elif any(w in lower_msg for w in ("debug", "debug code", "can you debug", "bug")):
                content = (
                    "Mock completion response: Yes, I can debug code across Python, TypeScript, Go, Rust, Java, and C++. "
                    "Share your code snippet, error message, or stack trace and I will identify the root cause, logic errors, "
                    "concurrency issues, or syntax bugs and provide a complete fix."
                )
            elif any(w in lower_msg for w in ("reply", "reply?", "are you there")):
                content = "Mock completion response: I am here and ready to help! What question, coding problem, or system architecture would you like to discuss?"
            elif any(
                w in lower_msg
                for w in (
                    "what all task",
                    "task can the smart ai gateway",
                    "feature",
                    "capabilities",
                    "what can you do",
                    "help",
                )
            ):
                content = (
                    "Mock completion response: Below is a high-level overview of tasks the **Smart AI Gateway** performs:\n\n"
                    "1. **Intelligent Dual-Agent Routing**: Automatically classifies task complexity in real time and routes to the Weak Agent (fast, cost-effective) or Strong Agent (deep reasoning, architecture, debugging).\n"
                    "2. **BYOK Multi-Provider Execution**: Executes real API requests against Groq, OpenAI, Google Gemini, Anthropic, or OpenAI-compatible backends using your own encrypted API keys.\n"
                    "3. **Cost & Latency Optimization**: Live token counting, rate-card cost calculation, and financial savings analytics.\n"
                    "4. **Production Resilience**: Circuit breakers, automatic retries with exponential backoff, and model fallback progressions."
                )
            elif "python" in lower_msg and "what is" in lower_msg:
                content = (
                    "Mock completion response: Python is a versatile, high-level, interpreted programming language known for its clean, "
                    "readable syntax. It is widely used in artificial intelligence, backend web development, data science, automation, "
                    "and systems engineering."
                )
            elif "recursion" in lower_msg:
                content = (
                    "Mock completion response: Recursion is a programming technique where a function solves a problem by calling itself with smaller inputs.\n\n"
                    "```python\ndef factorial(n: int) -> int:\n    if n <= 1:\n        return 1  # Base case\n    return n * factorial(n - 1)  # Recursive case\n```"
                )
            elif any(w in lower_msg for w in ("architecture", "distributed", "multi-agent")):
                content = (
                    "Mock completion response: ## Scalable Distributed Multi-Agent Architecture\n\n"
                    "A resilient distributed multi-agent system comprises:\n"
                    "1. **Decoupled Event Backbone**: Apache Kafka or NATS JetStream for asynchronous agent event streaming.\n"
                    "2. **Consensus & State Store**: Redis or Raft-based state synchronization across worker nodes.\n"
                    "3. **Dynamic Orchestrator**: Directed Acyclic Graph (DAG) workflow engine coordinating weak and strong agents.\n"
                    "4. **Observability**: Distributed tracing with OpenTelemetry, Prometheus metrics, and automated circuit breakers."
                )
            else:
                content = (
                    f"Mock completion response: Request successfully processed by gateway ({model_alias}). "
                    f"Task analyzed: '{last_user_message}'. The Smart AI Gateway is ready for your next prompt."
                )
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
            is_mock=True,
        )
