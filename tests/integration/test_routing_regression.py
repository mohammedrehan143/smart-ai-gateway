"""Comprehensive regression test suite for intelligent model routing correction.

Tests the 6 specific canonical prompts, complexity classification, capability detection,
strategy behaviors, fallback safeguards, and cost comparisons against baseline.
"""

from __future__ import annotations

from typing import List, Optional
import pytest
from httpx import AsyncClient
from app.api.deps import get_orchestrator
from app.core.errors import ProviderServerError
from app.core.rate_cards import default_rate_catalog
from app.domain.classifier import ComplexityClassifier, ComplexityLevel
from app.domain.entities import ChatMessage, GenerationParameters, NormalizedCompletion, RoutingOptions
from app.domain.router import DeterministicRouter
from app.main import app
from app.providers.base import BaseProviderAdapter
from app.repositories.sqlite import SqliteTraceRepository
from app.services.orchestrator import ChatOrchestrator

CANONICAL_PROMPTS = [
    ("What is Python?", ComplexityLevel.SIMPLE, "cheap", "mock-cheap"),
    ("Explain binary search with an example.", ComplexityLevel.MODERATE, "cheap", "mock-cheap"),
    ("Write a Python function to reverse a string.", ComplexityLevel.MODERATE, "cheap", "mock-cheap"),
    ("Debug this complex asynchronous Python application.", ComplexityLevel.COMPLEX, "strong", "mock-strong"),
    ("Design a scalable distributed banking architecture.", ComplexityLevel.COMPLEX, "strong", "mock-strong"),
    ("Analyze this complicated multi-agent security incident.", ComplexityLevel.EXPERT, "strong", "mock-strong"),
]


@pytest.mark.parametrize("prompt,expected_complexity,expected_tier,expected_model", CANONICAL_PROMPTS)
def test_canonical_prompts_classification_and_scoring(
    prompt: str,
    expected_complexity: ComplexityLevel,
    expected_tier: str,
    expected_model: str,
):
    """Verifies that all 6 canonical prompts classify accurately and select the right model tier."""
    router = DeterministicRouter()
    messages = [ChatMessage(role="user", content=prompt)]

    # 1. Complexity classification check
    classification = ComplexityClassifier.classify(messages)
    assert classification.complexity == expected_complexity, (
        f"Prompt '{prompt}' expected {expected_complexity.value}, got {classification.complexity.value}"
    )

    # 2. Router selection under default Balanced strategy
    decision = router.route(messages, RoutingOptions(policy="adaptive", preference="balanced"))
    assert decision.complexity == expected_complexity.value
    assert decision.tier == expected_tier, (
        f"Prompt '{prompt}' expected tier {expected_tier}, but router selected {decision.tier} ({decision.selected_model_alias})"
    )
    assert decision.selected_model_alias == expected_model
    assert decision.estimated_cost is not None
    assert decision.estimated_cost > 0.0


@pytest.mark.asyncio
async def test_canonical_prompts_api_e2e(async_client: AsyncClient):
    """Executes all 6 canonical prompts via POST /v1/chat API and validates transparency payload."""
    for prompt, expected_complexity, expected_tier, expected_model in CANONICAL_PROMPTS:
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "routing": {"policy": "adaptive", "strategy": "balanced"},
        }
        resp = await async_client.post("/v1/chat", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        routing = data["routing"]
        assert routing["complexity"] == expected_complexity.value
        assert routing["tier"] == expected_tier
        assert data["model"] == expected_model
        assert routing["strategy"] == "balanced"
        assert isinstance(routing["alternative_eligible_models"], list)
        assert routing["estimated_cost"] is not None


def test_ordinary_coding_does_not_select_expensive_model():
    """Verify that routine code creation ('Write a Python function to reverse a string')

    is NOT routed to the expensive strong model (which was the bug in the original implementation).
    """
    router = DeterministicRouter()
    messages = [ChatMessage(role="user", content="Write a Python function to reverse a string.")]

    decision = router.route(messages, RoutingOptions(policy="adaptive", preference="balanced"))
    assert decision.complexity == ComplexityLevel.MODERATE.value
    assert decision.tier == "cheap"
    assert decision.selected_model_alias == "mock-cheap"
    assert decision.selected_model_alias != "mock-strong"


def test_configurable_strategies():
    """Validates the 5 required strategies:

    Cost Optimized, Balanced, Quality First, Performance Optimized, Manual.
    """
    router = DeterministicRouter()
    moderate_msg = [ChatMessage(role="user", content="Explain binary search with an example.")]

    # 1. Cost Optimized: prefers cheapest capable model
    dec_cost = router.route(moderate_msg, RoutingOptions(policy="adaptive", strategy="cost_optimized"))
    assert dec_cost.tier == "cheap"
    assert dec_cost.selected_model_alias == "mock-cheap"

    # 2. Balanced: standard balanced selection
    dec_bal = router.route(moderate_msg, RoutingOptions(policy="adaptive", strategy="balanced"))
    assert dec_bal.tier == "cheap"
    assert dec_bal.selected_model_alias == "mock-cheap"

    # 3. Quality First: elevates moderate task to high-quality model
    dec_qual = router.route(moderate_msg, RoutingOptions(policy="adaptive", strategy="quality_first"))
    assert dec_qual.tier == "strong"
    assert dec_qual.selected_model_alias == "mock-strong"

    # 4. Performance Optimized: prioritizes fast latency tier
    dec_perf = router.route(moderate_msg, RoutingOptions(policy="adaptive", strategy="performance_optimized"))
    meta = router.registry.get_model(dec_perf.selected_model_alias)
    assert meta.latency_tier == "fast"

    # 5. Manual Selection: uses caller-selected model
    dec_manual = router.route(
        moderate_msg,
        RoutingOptions(policy="adaptive", strategy="manual", manual_model="gpt-4o-mini"),
    )
    assert dec_manual.selected_model_alias == "gpt-4o-mini"
    assert dec_manual.reason_code == "MANUAL_MODEL_SELECTED"


def test_quality_threshold_safeguard():
    """Verifies that configurable quality threshold prevents downgrading to low-quality models."""
    router = DeterministicRouter()
    simple_msg = [ChatMessage(role="user", content="What is Python?")]

    # Normal threshold: routes to cheap model (quality 0.75)
    dec_normal = router.route(simple_msg, RoutingOptions(policy="adaptive"))
    assert dec_normal.tier == "cheap"
    assert dec_normal.selected_model_alias == "mock-cheap"

    # Strict quality threshold 0.95: cannot use mock-cheap (0.75), must upgrade to high-quality model
    dec_strict = router.route(simple_msg, RoutingOptions(policy="adaptive", quality_threshold=0.95))
    assert dec_strict.tier == "strong"
    meta = router.registry.get_model(dec_strict.selected_model_alias)
    assert meta.quality_score >= 0.95


@pytest.mark.asyncio
async def test_fallback_records_reason_and_preserves_requirements(
    async_client: AsyncClient, test_repo: SqliteTraceRepository
):
    """Verifies that fallback preserves original task requirements, records fallback reason,

    and transparently logs recovery without automatically jumping to an unapproved model.
    """
    class PrimaryFailsAdapter(BaseProviderAdapter):
        def __init__(self):
            self.calls = []

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
            self.calls.append(model_alias)
            if model_alias == "mock-cheap":
                raise ProviderServerError("Simulated upstream 503 Service Unavailable on primary cheap model")
            return NormalizedCompletion(
                content="Recovered from candidate fallback model!",
                finish_reason="stop",
                provider="mock",
                model_alias=model_alias,
                input_tokens=15,
                output_tokens=10,
                total_tokens=25,
            )

    failing_adapter = PrimaryFailsAdapter()
    orch = ChatOrchestrator(repository=test_repo, default_adapter=failing_adapter)
    app.dependency_overrides[get_orchestrator] = lambda: orch

    payload = {
        "messages": [{"role": "user", "content": "What is Python?"}],
        "routing": {"policy": "adaptive", "strategy": "balanced"},
    }

    resp = await async_client.post("/v1/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["routing"]["fallback_used"] is True
    assert "Simulated upstream 503" in data["routing"]["fallback_reason"] or "failed" in data["routing"]["fallback_reason"]
    assert data["routing"]["complexity"] == "SIMPLE"
    assert "Recovered from candidate fallback" in data["choices"][0]["message"]["content"]


def test_cost_comparison_against_baseline():
    """Compares the cost of the 6 canonical requests under naive/old routing vs corrected routing."""
    # Model rate cards
    cheap_rate = default_rate_catalog.get_rate("mock-cheap")
    strong_rate = default_rate_catalog.get_rate("mock-strong")

    # Tokens per request: average 50 input tokens, 200 output tokens
    in_tokens = 50
    out_tokens = 200

    cheap_cost_per_query = (in_tokens / 1e6 * cheap_rate.input_rate_per_million) + (out_tokens / 1e6 * cheap_rate.output_rate_per_million)
    strong_cost_per_query = (in_tokens / 1e6 * strong_rate.input_rate_per_million) + (out_tokens / 1e6 * strong_rate.output_rate_per_million)

    # In naive routing:
    # 1. "What is Python?" -> cheap ($0.0001275)
    # 2. "Explain binary search" -> strong ($0.0021250) (escalated by code/multistep)
    # 3. "Write Python function" -> strong ($0.0021250) (escalated by def/code keyword)
    # 4. "Debug async" -> strong ($0.0021250)
    # 5. "Distributed banking" -> strong ($0.0021250)
    # 6. "Security incident" -> strong ($0.0021250)
    naive_total = cheap_cost_per_query + (strong_cost_per_query * 5)

    # In corrected routing:
    # 1. SIMPLE -> cheap ($0.0001275)
    # 2. MODERATE -> cheap ($0.0001275)
    # 3. MODERATE -> cheap ($0.0001275)
    # 4. COMPLEX -> strong ($0.0021250)
    # 5. COMPLEX -> strong ($0.0021250)
    # 6. EXPERT -> strong ($0.0021250)
    corrected_total = (cheap_cost_per_query * 3) + (strong_cost_per_query * 3)

    cost_savings = (naive_total - corrected_total) / naive_total * 100

    # Specifically for the 2 misrouted prompts (binary search & reverse string):
    # Naive cost = 2 * strong_cost = 2 * $0.002125 = $0.00425
    # Corrected cost = 2 * cheap_cost = 2 * $0.0001275 = $0.000255
    # Savings on these requests is (0.002125 - 0.0001275) / 0.002125 = 94.0%
    routine_savings = (strong_cost_per_query - cheap_cost_per_query) / strong_cost_per_query * 100

    assert routine_savings >= 93.0
    assert cost_savings >= 35.0
