"""OpenAI-compatible hosted provider adapter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import httpx

from app.core.errors import (
    InvalidRequestError,
    ProviderAuthError,
    ProviderServerError,
    RateLimitError,
    RequestTimeoutError,
)
from app.core.logging import get_logger
from app.domain.entities import ChatMessage, GenerationParameters, NormalizedCompletion
from app.domain.registry import registry
from app.providers.base import BaseProviderAdapter

logger = get_logger("providers.openai")


class OpenAICompatibleAdapter(BaseProviderAdapter):
    """Adapter for hosted OpenAI-compatible chat completion APIs."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.api_key = api_key or ""
        self.base_url = base_url.rstrip("/")
        self._custom_client = http_client

    @property
    def provider_name(self) -> str:
        return "openai"

    async def generate(
        self,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
        model_alias: str,
        timeout_seconds: float,
        tools: Optional[list] = None,
    ) -> NormalizedCompletion:
        model_meta = registry.get_model(model_alias)
        upstream_model = model_meta.upstream_model_id if model_meta else model_alias

        payload_messages = []
        for m in messages:
            msg_dict: Dict[str, Any] = {"role": m.role, "content": m.content}
            if m.name:
                msg_dict["name"] = m.name
            if m.tool_calls:
                msg_dict["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            payload_messages.append(msg_dict)

        payload: Dict[str, Any] = {
            "model": upstream_model,
            "messages": payload_messages,
            "temperature": parameters.temperature,
            "max_tokens": parameters.max_output_tokens,
        }

        if tools:
            payload["tools"] = tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        client = self._custom_client or httpx.AsyncClient(timeout=timeout_seconds)
        should_close = self._custom_client is None

        try:
            response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as te:
            raise RequestTimeoutError(f"Provider request timed out after {timeout_seconds}s") from te
        except httpx.RequestError as re:
            raise ProviderServerError(f"Network transport error contacting provider: {type(re).__name__}") from re
        finally:
            if should_close:
                await client.aclose()

        if response.status_code == 401 or response.status_code == 403:
            raise ProviderAuthError("Provider rejected authentication credentials")
        elif response.status_code == 429:
            retry_after_hdr = response.headers.get("Retry-After")
            retry_after_s = float(retry_after_hdr) if retry_after_hdr and retry_after_hdr.isdigit() else None
            raise RateLimitError("Provider rate limit reached", retry_after_s=retry_after_s)
        elif response.status_code >= 500:
            raise ProviderServerError(f"Provider returned 5xx server error ({response.status_code})")
        elif response.status_code >= 400:
            raise InvalidRequestError(f"Provider rejected request payload: {response.text[:200]}")

        try:
            data = response.json()
        except Exception as e:
            raise ProviderServerError("Failed to parse provider JSON response") from e

        choices = data.get("choices", [])
        if not choices:
            raise ProviderServerError("Provider response missing choices array")

        first_choice = choices[0]
        choice_msg = first_choice.get("message", {})
        content = choice_msg.get("content") or ""
        finish_reason = first_choice.get("finish_reason", "stop")
        tool_calls = choice_msg.get("tool_calls")

        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", input_tokens + output_tokens)
        raw_usage = "prompt_tokens" in usage

        return NormalizedCompletion(
            content=content,
            finish_reason=finish_reason,
            provider=self.provider_name,
            model_alias=model_alias,
            provider_request_id=data.get("id"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            raw_usage_available=raw_usage,
            tool_calls=tool_calls,
        )
