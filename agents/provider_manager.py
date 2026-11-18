"""Unified Multi-Provider API Abstraction for Real LLM Execution with Connection Pooling, Retries, and Circuit Breakers."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx

from app.core.config import settings
from app.core.errors import (
    InvalidRequestError,
    ProviderAuthError,
    ProviderServerError,
    RateLimitError,
    RequestTimeoutError,
)
from app.core.logging import get_logger
from app.core.network_security import validate_provider_base_url
from app.core.prompts import GATEWAY_SYSTEM_PROMPT, sanitize_llm_response
from app.domain.circuit_breaker import default_circuit_registry
from app.domain.retry import calculate_backoff, is_retryable_error

logger = get_logger("agents.provider_manager")

PROVIDER_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "anthropic": "https://api.anthropic.com/v1",
    "openai_compatible": "https://api.openai.com/v1",
}


@dataclass
class ProviderResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    provider: str
    latency_ms: int
    finish_reason: str = "stop"
    raw_response: Dict[str, Any] = field(default_factory=dict)


class ProviderManager:
    """Dispatches real API requests across OpenAI, Groq, Google Gemini, Anthropic, and OpenAI-compatible backends."""

    def __init__(self, default_timeout_s: float = 60.0):
        self.default_timeout_s = default_timeout_s
        self._client: Optional[httpx.AsyncClient] = None

    def _get_http_client(self, timeout: float) -> httpx.AsyncClient:
        """Returns or creates a pooled AsyncClient with connection reuse and keep-alive."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def resolve_base_url(self, provider: str, custom_base_url: Optional[str] = None) -> str:
        """Determines appropriate API endpoint base URL with SSRF protection."""
        if custom_base_url and custom_base_url.strip():
            validated = validate_provider_base_url(custom_base_url.strip())
            if validated:
                return validated
        p = provider.lower().strip()
        return PROVIDER_DEFAULT_BASE_URLS.get(p, "https://api.openai.com/v1").rstrip("/")

    def _build_headers(self, provider: str, api_key: str) -> Dict[str, str]:
        p = provider.lower().strip()
        if p == "anthropic":
            return {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _handle_error_response(self, response: httpx.Response, provider: str) -> None:
        """Translates HTTP error codes into categorized domain errors."""
        if response.is_success:
            return

        status = response.status_code
        err_text = response.text[:400]
        try:
            err_json = response.json()
            if "error" in err_json:
                err_detail = err_json["error"]
                if isinstance(err_detail, dict):
                    err_text = err_detail.get("message", err_text)
                else:
                    err_text = str(err_detail)
            elif "detail" in err_json:
                err_text = str(err_json["detail"])
        except Exception:
            pass

        if status in (401, 403):
            raise ProviderAuthError(f"Authentication failed for {provider}: {err_text}")
        elif status == 429:
            retry_after = response.headers.get("Retry-After")
            retry_s = float(retry_after) if retry_after and retry_after.isdigit() else 2.0
            raise RateLimitError(f"Rate limit exceeded for {provider}: {err_text}", retry_after_s=retry_s)
        elif status == 404:
            raise InvalidRequestError(f"Model or endpoint not found on {provider}: {err_text}")
        elif status >= 500:
            raise ProviderServerError(f"{provider} returned server error ({status}): {err_text}")
        else:
            raise InvalidRequestError(f"{provider} rejected request ({status}): {err_text}")

    async def test_connection(
        self,
        provider: str,
        api_key: str,
        model_id: str,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs a minimal connectivity and credential verification probe."""
        start = time.time()
        test_messages = [{"role": "user", "content": "Ping"}]
        try:
            res = await self.execute(
                provider=provider,
                api_key=api_key,
                model_id=model_id,
                messages=test_messages,
                temperature=0.0,
                max_tokens=5,
                base_url=base_url,
                timeout_seconds=15.0,
            )
            elapsed_ms = int((time.time() - start) * 1000)
            return {
                "success": True,
                "latency_ms": elapsed_ms,
                "message": f"Successfully verified connection to {provider} ({model_id})",
                "sample_response": res.content[:60],
            }
        except Exception as exc:
            elapsed_ms = int((time.time() - start) * 1000)
            return {
                "success": False,
                "latency_ms": elapsed_ms,
                "error": str(exc),
            }

    async def execute(
        self,
        provider: str,
        api_key: str,
        model_id: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_attempts: Optional[int] = None,
    ) -> ProviderResponse:
        """Executes a real prompt completion with exponential backoff and circuit breaker tracking."""
        p = provider.lower().strip()
        attempts_limit = max_attempts or getattr(settings, "MAX_PROVIDER_ATTEMPTS", 3)
        last_exception: Optional[Exception] = None

        for attempt in range(1, attempts_limit + 1):
            try:
                resp = await self._execute_single_attempt(
                    provider=p,
                    api_key=api_key,
                    model_id=model_id,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                )
                default_circuit_registry.record_outcome(model_id, success=True)
                return resp
            except Exception as exc:
                last_exception = exc
                is_retryable = is_retryable_error(exc) or isinstance(exc, (httpx.TimeoutException, httpx.RequestError))
                if not is_retryable or attempt >= attempts_limit:
                    default_circuit_registry.record_outcome(model_id, success=False, error=exc)
                    raise exc

                retry_after_s = getattr(exc, "retry_after_s", None)
                backoff_delay = calculate_backoff(
                    attempt, retry_after_s=retry_s if (retry_s := retry_after_s) else None
                )
                logger.warning(
                    f"Provider execution attempt {attempt} for {p}:{model_id} failed ({exc}). Retrying in {backoff_delay:.2f}s..."
                )
                await asyncio.sleep(backoff_delay)

        if last_exception:
            raise last_exception
        raise ProviderServerError(f"Failed to execute request on {p}:{model_id} after {attempts_limit} attempts")

    async def _execute_single_attempt(
        self,
        provider: str,
        api_key: str,
        model_id: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> ProviderResponse:
        start_time = time.time()
        timeout = timeout_seconds or self.default_timeout_s
        resolved_base = self.resolve_base_url(provider, base_url)

        has_system = any(m.get("role") == "system" for m in messages)
        formatted_messages = list(messages)
        if not has_system:
            formatted_messages = [{"role": "system", "content": GATEWAY_SYSTEM_PROMPT}] + formatted_messages

        if provider == "anthropic" and "api.anthropic.com" in resolved_base:
            return await self._execute_anthropic_native(
                api_key=api_key,
                model_id=model_id,
                messages=formatted_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                base_url=resolved_base,
                timeout=timeout,
                start_time=start_time,
            )

        url = f"{resolved_base}/chat/completions"
        headers = self._build_headers(provider, api_key)

        is_modern_or_reasoning = (
            "openai/" in model_id.lower()
            or "gpt-oss" in model_id.lower()
            or model_id.lower().startswith("o1")
            or model_id.lower().startswith("o3")
            or "deepseek-r1" in model_id.lower()
        )

        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": formatted_messages,
            "stream": False,
        }
        if is_modern_or_reasoning:
            payload["max_completion_tokens"] = max_tokens
            if "gpt-oss" in model_id.lower() or "openai/" in model_id.lower():
                payload["reasoning_effort"] = "medium"
            if temperature is not None:
                payload["temperature"] = temperature
        else:
            payload["max_tokens"] = max_tokens
            if temperature is not None:
                payload["temperature"] = temperature

        client = self._get_http_client(timeout)
        try:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 400 and (
                "max_completion_tokens" in response.text or "max_tokens" in response.text
            ):
                if "max_tokens" in payload:
                    payload.pop("max_tokens", None)
                    payload["max_completion_tokens"] = max_tokens
                    response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as te:
            raise RequestTimeoutError(f"Request to {provider} timed out after {timeout}s") from te
        except httpx.RequestError as re:
            raise ProviderServerError(f"Network transport failure contacting {provider}: {re}") from re

        self._handle_error_response(response, provider)
        data = response.json()

        choices = data.get("choices", [])
        if not choices:
            raise ProviderServerError(f"Malformed response from {provider}: no choices array returned")

        first_msg = choices[0].get("message", {})
        raw_content = first_msg.get("content") or ""
        content = sanitize_llm_response(raw_content)
        finish_reason = choices[0].get("finish_reason", "stop")
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        latency_ms = int((time.time() - start_time) * 1000)

        return ProviderResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model=model_id,
            provider=provider,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            raw_response=data,
        )

    async def _execute_anthropic_native(
        self,
        api_key: str,
        model_id: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        base_url: str,
        timeout: float,
        start_time: float,
    ) -> ProviderResponse:
        url = f"{base_url}/messages"
        headers = self._build_headers("anthropic", api_key)

        system_text = ""
        user_assistant_messages = []
        for m in messages:
            if m.get("role") == "system":
                system_text = m.get("content", "")
            else:
                user_assistant_messages.append({"role": m.get("role"), "content": m.get("content")})

        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": user_assistant_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_text:
            payload["system"] = system_text

        client = self._get_http_client(timeout)
        try:
            response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as te:
            raise RequestTimeoutError(f"Anthropic request timed out after {timeout}s") from te
        except httpx.RequestError as re:
            raise ProviderServerError(f"Network error contacting Anthropic: {re}") from re

        self._handle_error_response(response, "anthropic")
        data = response.json()

        content_blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        usage = data.get("usage", {})
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)
        latency_ms = int((time.time() - start_time) * 1000)

        return ProviderResponse(
            content=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model=model_id,
            provider="anthropic",
            latency_ms=latency_ms,
            finish_reason=data.get("stop_reason", "end_turn"),
            raw_response=data,
        )

    async def stream_execute(
        self,
        provider: str,
        api_key: str,
        model_id: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        p = provider.lower().strip()
        timeout = timeout_seconds or self.default_timeout_s
        resolved_base = self.resolve_base_url(p, base_url)
        url = f"{resolved_base}/chat/completions"
        headers = self._build_headers(p, api_key)

        is_modern_or_reasoning = (
            "openai/" in model_id.lower()
            or "gpt-oss" in model_id.lower()
            or model_id.lower().startswith("o1")
            or model_id.lower().startswith("o3")
            or "deepseek-r1" in model_id.lower()
        )

        has_system = any(m.get("role") == "system" for m in messages)
        formatted_messages = list(messages)
        if not has_system:
            formatted_messages = [{"role": "system", "content": GATEWAY_SYSTEM_PROMPT}] + formatted_messages

        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": formatted_messages,
            "stream": True,
        }
        if is_modern_or_reasoning:
            payload["max_completion_tokens"] = max_tokens
            if "gpt-oss" in model_id.lower() or "openai/" in model_id.lower():
                payload["reasoning_effort"] = "medium"
            if temperature is not None:
                payload["temperature"] = temperature
        else:
            payload["max_tokens"] = max_tokens
            if temperature is not None:
                payload["temperature"] = temperature

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                self._handle_error_response(resp, p)
                async for line in resp.aiter_lines():
                    if not line or not line.strip():
                        continue
                    line_str = line.strip()
                    if line_str.startswith("data: "):
                        raw_data = line_str[6:].strip()
                        if raw_data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw_data)
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                if not delta.get("content") and (
                                    delta.get("reasoning") or delta.get("reasoning_content")
                                ):
                                    continue
                            yield chunk
                        except json.JSONDecodeError:
                            continue


# Global singleton instance
default_provider_manager = ProviderManager()
