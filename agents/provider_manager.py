"""Unified Multi-Provider API Abstraction for Real LLM Execution."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx

from app.core.prompts import GATEWAY_SYSTEM_PROMPT, sanitize_llm_response

from app.core.errors import (
    InvalidRequestError,
    ProviderAuthError,
    ProviderServerError,
    RateLimitError,
    RequestTimeoutError,
)
from app.core.logging import get_logger

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

    def resolve_base_url(self, provider: str, custom_base_url: Optional[str] = None) -> str:
        """Determines appropriate API endpoint base URL."""
        if custom_base_url and custom_base_url.strip():
            return custom_base_url.strip().rstrip("/")
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
        # OpenAI, Groq, Google OpenAI-compatible, custom OpenAI-compatible
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
    ) -> ProviderResponse:
        """Executes a real non-streaming prompt completion against the upstream provider."""
        start_time = time.time()
        p = provider.lower().strip()
        timeout = timeout_seconds or self.default_timeout_s
        resolved_base = self.resolve_base_url(p, base_url)

        # Ensure standard system prompt is present to prevent model identity confusion or policy leak
        has_system = any(m.get("role") == "system" for m in messages)
        formatted_messages = list(messages)
        if not has_system:
            formatted_messages = [{"role": "system", "content": GATEWAY_SYSTEM_PROMPT}] + formatted_messages

        if p == "anthropic" and "api.anthropic.com" in resolved_base:
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

        # Standard OpenAI-compatible format (OpenAI, Groq, Google OpenAI endpoint, Custom)
        url = f"{resolved_base}/chat/completions"
        headers = self._build_headers(p, api_key)
        
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

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                # Auto-recovery: If provider rejects max_tokens in favor of max_completion_tokens
                if response.status_code == 400 and ("max_completion_tokens" in response.text or "max_tokens" in response.text):
                    if "max_tokens" in payload:
                        payload.pop("max_tokens", None)
                        payload["max_completion_tokens"] = max_tokens
                        response = await client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException as te:
                raise RequestTimeoutError(f"Request to {p} timed out after {timeout}s") from te
            except httpx.RequestError as re:
                raise ProviderServerError(f"Network transport failure contacting {p}: {re}") from re

            self._handle_error_response(response, p)
            data = response.json()

        choices = data.get("choices", [])
        if not choices:
            raise ProviderServerError(f"Malformed response from {p}: no choices array returned")

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
            provider=p,
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
        """Executes request via native Anthropic Messages API."""
        url = f"{base_url}/messages"
        headers = self._build_headers("anthropic", api_key)

        # Separate system message if present
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

        async with httpx.AsyncClient(timeout=timeout) as client:
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
        """Streams real token chunks from upstream provider over Server-Sent Events."""
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

        # Ensure standard system prompt is present to prevent identity confusion or policy leak
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
                                # Exclude pure internal reasoning or thought chunks
                                if not delta.get("content") and (delta.get("reasoning") or delta.get("reasoning_content")):
                                    continue
                            yield chunk
                        except json.JSONDecodeError:
                            continue


# Global singleton instance
default_provider_manager = ProviderManager()
