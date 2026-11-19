"""Weak Agent: Handles simple, inexpensive, low-complexity, routine tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional
from agents.credential_manager import CredentialManager, default_credential_manager
from agents.provider_manager import ProviderManager, ProviderResponse, default_provider_manager
from app.core.cost import default_cost_calculator
from app.core.errors import InvalidRequestError
from app.core.logging import get_logger

logger = get_logger("agents.weak_agent")


@dataclass
class AgentExecutionResult:
    agent: str  # "weak" or "strong"
    content: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int
    cost: float
    finish_reason: str = "stop"
    raw_response: Optional[Dict[str, Any]] = None
    reasoning_effort: Optional[str] = "none"
    plan: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    verification: Optional[Dict[str, Any]] = None
    is_mock: bool = False


class WeakAgent:
    """Agent specialized for simple, high-velocity, cost-effective prompt executions."""

    AGENT_TYPE = "weak"
    DEFAULT_INPUT_RATE = 0.15  # $0.15 / 1M tokens
    DEFAULT_OUTPUT_RATE = 0.60  # $0.60 / 1M tokens

    def __init__(
        self,
        credential_mgr: Optional[CredentialManager] = None,
        provider_mgr: Optional[ProviderManager] = None,
    ):
        self.credential_mgr = credential_mgr or default_credential_manager
        self.provider_mgr = provider_mgr or default_provider_manager

    def is_configured(self, user_id: str) -> bool:
        """Checks if the Weak Agent has credentials configured."""
        return self.credential_mgr.is_agent_ready(user_id, "weak")

    def _get_config(self, user_id: str):
        config = self.credential_mgr.get_agent_config(user_id, "weak")
        if not config:
            raise InvalidRequestError(
                "Weak Agent is not configured. Please configure a provider and API key in Agent Settings."
            )
        if not config.is_enabled:
            raise InvalidRequestError("Weak Agent is currently disabled.")
        return config

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int, model_id: str) -> float:
        """Computes cost in USD using model rate card or weak tier baseline."""
        calc = default_cost_calculator.calculate(model_id, prompt_tokens, completion_tokens)
        if calc and calc.estimated_cost is not None:
            return calc.estimated_cost
        return (prompt_tokens * (self.DEFAULT_INPUT_RATE / 1_000_000.0)) + (
            completion_tokens * (self.DEFAULT_OUTPUT_RATE / 1_000_000.0)
        )

    async def execute(
        self,
        user_id: str,
        prompt: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
    ) -> AgentExecutionResult:
        """Executes prompt using the Weak Agent's configured provider & model."""
        config = self._get_config(user_id)
        api_key = config.get_plaintext_key()

        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": prompt})

        temperature = temperature_override if temperature_override is not None else config.temperature
        max_tokens = max_tokens_override if max_tokens_override is not None else config.max_tokens

        logger.info(
            "Executing Weak Agent prompt",
            extra={"user_id": user_id, "provider": config.provider, "model": config.model_id},
        )

        response: ProviderResponse = await self.provider_mgr.execute(
            provider=config.provider,
            api_key=api_key,
            model_id=config.model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=config.base_url,
        )

        cost = self.calculate_cost(response.prompt_tokens, response.completion_tokens, config.model_id)
        is_mock = (config.provider == "mock") or ("mock" in config.model_id.lower())
        actual_provider = "mock" if is_mock else config.provider

        return AgentExecutionResult(
            agent=self.AGENT_TYPE,
            content=response.content,
            provider=actual_provider,
            model=config.model_id,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            latency_ms=response.latency_ms,
            cost=cost,
            finish_reason=response.finish_reason,
            raw_response=response.raw_response,
            reasoning_effort="none",
            is_mock=is_mock,
        )

    async def stream_execute(
        self,
        user_id: str,
        prompt: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streams real token chunks using Weak Agent."""
        config = self._get_config(user_id)
        api_key = config.get_plaintext_key()

        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": prompt})

        temperature = temperature_override if temperature_override is not None else config.temperature
        max_tokens = max_tokens_override if max_tokens_override is not None else config.max_tokens

        async for chunk in self.provider_mgr.stream_execute(
            provider=config.provider,
            api_key=api_key,
            model_id=config.model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=config.base_url,
        ):
            yield chunk


default_weak_agent = WeakAgent()
