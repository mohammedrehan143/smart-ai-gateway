"""HTTPX Gateway Client for communication with Smart AI Gateway API."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, Generator, List, Optional
import httpx

from smart_ai_cli.auth import AuthManager, default_auth_manager
from smart_ai_cli.config import ConfigManager, default_config_manager
from smart_ai_cli.schemas import (
    AuthVerifyResponse,
    BenchmarkRunResponse,
    CostAnalyticsResponse,
    ModelsResponse,
    RoutingDecisionsResponse,
    UsageAnalyticsResponse,
)


class GatewayClientError(Exception):
    """Base exception for gateway client failures."""
    pass


class GatewayConnectionError(GatewayClientError):
    """Raised when unable to establish connection to the gateway."""
    pass


class AuthenticationError(GatewayClientError):
    """Raised on invalid, missing, or expired API credentials (401/403)."""
    pass


class RateLimitError(GatewayClientError):
    """Raised on HTTP 429 Too Many Requests."""
    pass


class GatewayServerError(GatewayClientError):
    """Raised on HTTP 5xx Gateway errors."""
    pass


class GatewayClient:
    """Robust client communicating with Smart AI Gateway endpoints."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        config_manager: Optional[ConfigManager] = None,
        auth_manager: Optional[AuthManager] = None,
    ):
        self.config_mgr = config_manager or default_config_manager
        self.auth_mgr = auth_manager or default_auth_manager

        config = self.config_mgr.load_config()
        env_url = os.environ.get("SMART_AI_GATEWAY_URL") or os.environ.get("GATEWAY_URL")
        self.base_url = (base_url or env_url or config.gateway_url).rstrip("/")
        self.api_key = api_key if api_key is not None else self.auth_mgr.get_api_key()
        self.timeout = timeout if timeout is not None else config.timeout_seconds

    def _headers(self, custom_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "SmartAI-CLI/0.1.0",
            "X-Request-ID": f"cli_{uuid.uuid4().hex[:12]}",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if custom_headers:
            headers.update(custom_headers)
        return headers

    def _handle_response_error(self, response: httpx.Response) -> None:
        if response.is_success:
            return

        status = response.status_code
        err_msg = f"HTTP {status}"
        try:
            err_json = response.json()
            if "error" in err_json and isinstance(err_json["error"], dict):
                err_msg = err_json["error"].get("message", err_msg)
            elif "detail" in err_json:
                detail = err_json["detail"]
                if isinstance(detail, dict) and "error" in detail:
                    err_msg = detail["error"].get("message", err_msg)
                else:
                    err_msg = str(detail)
        except Exception:
            err_msg = response.text or err_msg

        if status in (401, 403):
            raise AuthenticationError(f"Authentication failed: {err_msg}")
        elif status == 429:
            raise RateLimitError(f"Rate limit exceeded: {err_msg}")
        elif status >= 500:
            raise GatewayServerError(f"Gateway server error ({status}): {err_msg}")
        else:
            raise GatewayClientError(f"Request failed ({status}): {err_msg}")

    # --- Health & Connectivity ---

    def health_live(self) -> Dict[str, Any]:
        """Checks container liveness."""
        url = f"{self.base_url}/health/live"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers())
                self._handle_response_error(resp)
                return resp.json()
        except httpx.ConnectError as exc:
            raise GatewayConnectionError(f"Cannot connect to Gateway at {self.base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise GatewayConnectionError(f"Gateway connection timed out after {self.timeout}s") from exc

    def health_ready(self) -> Dict[str, Any]:
        """Checks database readiness."""
        url = f"{self.base_url}/health/ready"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers())
                self._handle_response_error(resp)
                return resp.json()
        except httpx.ConnectError as exc:
            raise GatewayConnectionError(f"Cannot connect to Gateway at {self.base_url}: {exc}") from exc

    def verify_auth(self) -> AuthVerifyResponse:
        """Verifies currently configured credentials."""
        url = f"{self.base_url}/v1/auth/verify"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers())
                self._handle_response_error(resp)
                return AuthVerifyResponse(**resp.json())
        except httpx.ConnectError as exc:
            raise GatewayConnectionError(f"Cannot connect to Gateway at {self.base_url}: {exc}") from exc

    # --- Models & Registry ---

    def list_models(self) -> ModelsResponse:
        """Retrieves list of registered models with capabilities and rate cards."""
        url = f"{self.base_url}/v1/models"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers())
                self._handle_response_error(resp)
                return ModelsResponse(**resp.json())
        except httpx.ConnectError as exc:
            raise GatewayConnectionError(f"Cannot connect to Gateway at {self.base_url}: {exc}") from exc

    # --- Usage & Cost Analytics ---

    def get_usage(self, since: Optional[float] = None, limit: int = 50) -> UsageAnalyticsResponse:
        """Fetches aggregated usage metrics."""
        url = f"{self.base_url}/v1/analytics/usage"
        params: Dict[str, Any] = {"limit": limit}
        if since is not None:
            params["since"] = since

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers(), params=params)
                self._handle_response_error(resp)
                return UsageAnalyticsResponse(**resp.json())
        except httpx.ConnectError as exc:
            raise GatewayConnectionError(f"Cannot connect to Gateway at {self.base_url}: {exc}") from exc

    def get_cost(self, since: Optional[float] = None) -> CostAnalyticsResponse:
        """Fetches financial cost analytics."""
        url = f"{self.base_url}/v1/analytics/cost"
        params: Dict[str, Any] = {}
        if since is not None:
            params["since"] = since

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers(), params=params)
                self._handle_response_error(resp)
                return CostAnalyticsResponse(**resp.json())
        except httpx.ConnectError as exc:
            raise GatewayConnectionError(f"Cannot connect to Gateway at {self.base_url}: {exc}") from exc

    # --- Routing Decisions ---

    def get_routing_decisions(self, limit: int = 20, trace_id: Optional[str] = None) -> RoutingDecisionsResponse:
        """Queries recent auto-routing decisions."""
        url = f"{self.base_url}/v1/routing/decisions"
        params: Dict[str, Any] = {"limit": limit}
        if trace_id:
            params["trace_id"] = trace_id

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers(), params=params)
                self._handle_response_error(resp)
                return RoutingDecisionsResponse(**resp.json())
        except httpx.ConnectError as exc:
            raise GatewayConnectionError(f"Cannot connect to Gateway at {self.base_url}: {exc}") from exc

    # --- Benchmarking ---

    def run_benchmark(
        self,
        policies: Optional[List[str]] = None,
        sample_size: Optional[int] = None,
    ) -> BenchmarkRunResponse:
        """Triggers evaluation benchmark execution."""
        url = f"{self.base_url}/v1/benchmark/run"
        payload: Dict[str, Any] = {
            "policies": policies or ["adaptive", "always_cheap", "always_strong"],
        }
        if sample_size:
            payload["sample_size"] = sample_size

        try:
            with httpx.Client(timeout=max(self.timeout, 120.0)) as client:
                resp = client.post(url, headers=self._headers(), json=payload)
                self._handle_response_error(resp)
                return BenchmarkRunResponse(**resp.json())
        except httpx.ConnectError as exc:
            raise GatewayConnectionError(f"Cannot connect to Gateway at {self.base_url}: {exc}") from exc

    # --- Chat Completions & Streaming ---

    def chat(
        self,
        messages: List[Dict[str, str]],
        policy: str = "adaptive",
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """Executes a standard non-streaming chat completion."""
        url = f"{self.base_url}/v1/chat"
        payload = {
            "messages": messages,
            "routing": {"policy": policy},
            "parameters": {
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            },
            "stream": False,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, headers=self._headers(), json=payload)
                self._handle_response_error(resp)
                return resp.json()
        except httpx.ConnectError as exc:
            raise GatewayConnectionError(f"Cannot connect to Gateway at {self.base_url}: {exc}") from exc

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        policy: str = "adaptive",
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> Generator[Dict[str, Any], None, None]:
        """Streams chat completion tokens and metadata chunks over Server-Sent Events."""
        url = f"{self.base_url}/v1/chat"
        payload = {
            "messages": messages,
            "routing": {"policy": policy},
            "parameters": {
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            },
            "stream": True,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", url, headers=self._headers(), json=payload) as response:
                    self._handle_response_error(response)
                    content_type = response.headers.get("content-type", "")
                    if "text/event-stream" not in content_type:
                        # Fallback if server returned standard JSON instead of SSE
                        raw_text = "".join(response.iter_text())
                        data = json.loads(raw_text)
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        yield {"choices": [{"delta": {"content": content}}]}
                        yield data
                        return

                    for line in response.iter_lines():
                        if not line or not line.strip():
                            continue
                        line_str = line.strip()
                        if line_str.startswith("data: "):
                            raw_data = line_str[6:].strip()
                            if raw_data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(raw_data)
                                yield chunk
                            except json.JSONDecodeError:
                                continue
        except httpx.ConnectError as exc:
            raise GatewayConnectionError(f"Cannot connect to Gateway at {self.base_url}: {exc}") from exc
