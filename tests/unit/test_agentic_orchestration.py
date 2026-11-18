"""Comprehensive unit and integration tests for Smart AI Gateway Agentic Orchestration Platform."""

from __future__ import annotations

import time
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret, redact_secrets_from_text
from app.core.observability import ObservabilityTracer
from app.domain.agentic_planner import AgenticTaskPlanner, ExecutionMode
from app.domain.bandit_router import ContextualBanditRouter
from app.domain.budget import BudgetController
from app.domain.byok import BYOKManager
from app.domain.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from app.domain.classifier import ComplexityLevel
from app.domain.collaboration import CollaborationExecutionEngine
from app.domain.entities import ChatMessage, GenerationParameters, NormalizedCompletion
from app.domain.evaluator import ResponseQualityEvaluator
from app.domain.intent_engine import IntentIntelligenceEngine, TaskCategory
from app.main import app
from app.providers.mock import MockProviderAdapter
from app.services.semantic_cache import AdvancedSemanticCache


# ==============================================================================
# 1. Security & BYOK Encryption Tests
# ==============================================================================
def test_crypto_encryption_and_decryption():
    raw_key = "sk-proj-super-secret-openai-api-key-1234567890"
    encrypted = encrypt_secret(raw_key)
    assert encrypted != raw_key
    assert len(encrypted) > 20

    decrypted = decrypt_secret(encrypted)
    assert decrypted == raw_key


def test_crypto_masking_and_redaction():
    raw_key = "sk-proj-super-secret-openai-api-key-1234567890"
    masked = mask_secret(raw_key)
    assert masked.startswith("sk-")
    assert masked.endswith("7890")
    assert "..." in masked
    assert "super-secret" not in masked

    log_message = f"User connected with key {raw_key} to provider"
    redacted = redact_secrets_from_text(log_message, [raw_key])
    assert raw_key not in redacted
    assert "[REDACTED_SECRET]" in redacted


def test_byok_manager_lifecycle():
    byok = BYOKManager()
    user_id = "test_user_byok_1"
    provider = "anthropic"
    api_key = "sk-ant-test-key-9988776655"

    # Store
    cred = byok.store_credential(user_id=user_id, provider=provider, api_key=api_key)
    assert cred.provider == provider
    assert cred.masked_key.endswith("6655")

    # Retrieve decrypted
    retrieved_key, base_url = byok.get_decrypted_credential(user_id=user_id, provider=provider)
    assert retrieved_key == api_key
    assert base_url is None

    # List
    creds = byok.list_credentials(user_id=user_id)
    assert len(creds) == 1
    assert creds[0]["provider"] == provider

    # Tenant isolation - different user sees nothing
    other_creds = byok.list_credentials(user_id="other_user")
    assert len(other_creds) == 0

    # Delete
    deleted = byok.delete_credential(user_id=user_id, provider=provider)
    assert deleted is True
    post_delete = byok.list_credentials(user_id=user_id)
    assert len(post_delete) == 0


# ==============================================================================
# 2. Intent & Task Intelligence Tests
# ==============================================================================
def test_intent_engine_multi_dimensional_profiling():
    engine = IntentIntelligenceEngine()

    # Coding task
    coding_msgs = [
        ChatMessage(role="user", content="Write a python function to compute fibonacci numbers with memoization.")
    ]
    coding_profile = engine.analyze(coding_msgs)
    assert coding_profile.category == TaskCategory.CODING
    assert coding_profile.output_format == "code"
    assert (
        "code_simple" in coding_profile.required_capabilities or "complex_code" in coding_profile.required_capabilities
    )

    # Mathematical task
    math_msgs = [
        ChatMessage(
            role="user",
            content="Calculate step-by-step the surface integral of vector field F(x, y, z) = (2x, -y, z^2) over the closed boundary of an ellipsoid x^2/a^2 + y^2/b^2 + z^2/c^2 = 1. Prove convergence rigorously using Gauss divergence theorem and detail each integration boundary step across Cartesian and spherical coordinates.",
        )
    ]
    math_profile = engine.analyze(math_msgs)
    assert math_profile.category == TaskCategory.MATHEMATICS
    assert math_profile.complexity in (ComplexityLevel.MODERATE, ComplexityLevel.COMPLEX)

    # Deep Architecture Reasoning task
    arch_msgs = [
        ChatMessage(role="user", content="Design a scalable distributed banking architecture with Raft consensus.")
    ]
    arch_profile = engine.analyze(arch_msgs)
    assert arch_profile.category in (TaskCategory.REASONING, TaskCategory.CODING)
    assert arch_profile.complexity in (ComplexityLevel.COMPLEX, ComplexityLevel.EXPERT)
    assert arch_profile.quality_expectation >= 0.85

    # Ambiguity score check
    vague_msgs = [ChatMessage(role="user", content="help me")]
    vague_profile = engine.analyze(vague_msgs)
    assert vague_profile.ambiguity_score > 0.3


# ==============================================================================
# 3. Reliability & Circuit Breaker Tests
# ==============================================================================
def test_circuit_breaker_transitions():
    cfg = CircuitBreakerConfig(failure_threshold=3, cooldown_seconds=0.1, half_open_trials=2)
    cb = CircuitBreaker(key="test-model", config=cfg)
    assert cb.state == CircuitState.CLOSED
    assert cb.is_available() is True

    # Record 2 failures -> still closed
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.is_available() is True

    # 3rd failure -> trips to OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.is_available() is False

    # Wait for cooldown -> transitions to HALF_OPEN
    time.sleep(0.15)
    assert cb.is_available() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Successful probes reset to CLOSED
    cb.record_success()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.is_available() is True


def test_circuit_breaker_half_open_failure():
    cfg = CircuitBreakerConfig(failure_threshold=2, cooldown_seconds=0.05, half_open_trials=2)
    cb = CircuitBreaker(key="test-model-2", config=cfg)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    time.sleep(0.06)
    assert cb.is_available() is True
    assert cb.state == CircuitState.HALF_OPEN

    # A single failure in HALF_OPEN trips immediately back to OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.is_available() is False


# ==============================================================================
# 4. Contextual Bandit Adaptive Learning Tests
# ==============================================================================
def test_bandit_reward_computation():
    router = ContextualBanditRouter()

    # High quality, low latency, low cost -> high reward
    r_high = router.compute_reward(quality_score=0.95, latency_ms=120.0, cost=0.0001, success=True, fallback_used=False)
    assert r_high > 0.75

    # Failure / fallback penalty -> low reward
    r_low = router.compute_reward(quality_score=0.30, latency_ms=4500.0, cost=0.02, success=False, fallback_used=True)
    assert r_low < 0.25


def test_bandit_arm_learning_and_decay():
    router = ContextualBanditRouter(min_sample_threshold=2)
    cat = "coding"
    model = "mock-cheap"

    # Initial state
    arm = router.get_arm(cat, model)
    assert arm.trials == 0

    # Provide 3 positive feedbacks
    router.record_feedback(cat, model, quality_score=0.90, latency_ms=100.0, cost=0.0002, success=True)
    router.record_feedback(cat, model, quality_score=0.95, latency_ms=110.0, cost=0.0002, success=True)
    router.record_feedback(cat, model, quality_score=0.92, latency_ms=90.0, cost=0.0002, success=True)

    arm = router.get_arm(cat, model)
    assert arm.trials == 3
    assert arm.avg_reward > 0.70

    # Test reset
    router.reset()
    assert len(router.get_statistics()) == 0


# ==============================================================================
# 5. Agentic Planning & Multi-Model Collaboration Tests
# ==============================================================================
def test_agentic_task_planner_decision_graph():
    planner = AgenticTaskPlanner()
    engine = IntentIntelligenceEngine()

    # Simple prompt -> Direct execution mode
    simple_p = engine.analyze([ChatMessage(role="user", content="What is Python?")])
    plan_simple = planner.create_plan(simple_p, "mock-cheap", "mock-strong", "mock-cheap")
    assert plan_simple.mode == ExecutionMode.DIRECT
    assert len(plan_simple.steps) == 1

    # Complex coding -> Collaborative code verification mode
    code_p = engine.analyze(
        [ChatMessage(role="user", content="Write a Python script to parse complex ELF binary headers.")]
    )
    plan_code = planner.create_plan(
        code_p,
        "mock-cheap",
        "mock-strong",
        "mock-cheap",
        collaboration_requested=True,
        collaboration_strategy="code_verification",
    )
    assert plan_code.mode == ExecutionMode.COLLABORATIVE
    assert plan_code.strategy == "code_verification"
    assert len(plan_code.steps) == 2
    assert plan_code.steps[1].action == "verify_code"


@pytest.mark.asyncio
async def test_collaboration_engine_peer_review():
    adapter = MockProviderAdapter()
    planner = AgenticTaskPlanner()
    intent_eng = IntentIntelligenceEngine()

    deep_prompt = "Analyze this complicated multi-agent security incident: unauthorized lateral movement and token exfiltration detected across AWS IAM roles."
    profile = intent_eng.analyze([ChatMessage(role="user", content=deep_prompt)])
    plan = planner.create_plan(
        profile,
        "mock-cheap",
        "mock-strong",
        "mock-cheap",
        collaboration_requested=True,
        collaboration_strategy="peer_review",
    )

    result_resp, executed_steps = await CollaborationExecutionEngine.execute_plan(
        plan=plan,
        messages=[ChatMessage(role="user", content=deep_prompt)],
        parameters=GenerationParameters(),
        adapter=adapter,
        timeout_seconds=10.0,
    )

    assert len(executed_steps) in (2, 3)
    assert all(s.status == "success" for s in executed_steps)
    assert result_resp.content is not None


# ==============================================================================
# 6. Response Quality Evaluator Tests
# ==============================================================================
def test_response_evaluator_valid_code():
    python_code = "```python\n# Function to add numbers\ndef add(a, b):\n    return a + b\n```"
    prompt_msgs = [ChatMessage(role="user", content="Write a function to add two numbers")]

    result = ResponseQualityEvaluator.evaluate(
        prompt_messages=prompt_msgs,
        response_text=python_code,
        expected_format="code",
        quality_threshold=0.6,
    )

    assert result.passed is True
    assert result.code_correctness_score > 0.8
    assert result.relevance_score > 0.3
    assert result.should_escalate is False


def test_response_evaluator_syntax_error():
    broken_code = "```python\ndef broken(\n    return 42\n```"
    prompt_msgs = [ChatMessage(role="user", content="Write a broken function")]

    result = ResponseQualityEvaluator.evaluate(
        prompt_messages=prompt_msgs,
        response_text=broken_code,
        expected_format="code",
        quality_threshold=0.8,
    )

    assert result.code_correctness_score < 0.5
    assert result.should_escalate is True


def test_response_evaluator_json_schema():
    valid_json = '{"user": "alice", "score": 95}'
    prompt_msgs = [ChatMessage(role="user", content="Generate JSON output")]

    result = ResponseQualityEvaluator.evaluate(
        prompt_messages=prompt_msgs,
        response_text=valid_json,
        expected_format="json",
    )
    assert result.format_validity_score > 0.8


# ==============================================================================
# 7. Proactive Budget Controller Tests
# ==============================================================================
def test_budget_controller_caps_and_spend():
    controller = BudgetController()
    user_id = "tenant_finance"
    project_id = "project_alpha"

    # Set per-request cap to $0.01 and daily budget to $0.05
    controller.set_budget(
        user_id=user_id,
        project_id=project_id,
        max_cost_per_request=0.01,
        daily_budget=0.05,
    )

    # 1. Check acceptable cost
    ok, err = controller.check_budget_available(user_id=user_id, project_id=project_id, estimated_cost=0.005)
    assert ok is True
    assert err is None

    # 2. Check cost exceeding per-request cap
    ok, err = controller.check_budget_available(user_id=user_id, project_id=project_id, estimated_cost=0.015)
    assert ok is False
    assert "exceeds per-request limit" in err

    # 3. Simulate spend accumulation towards daily cap
    controller.record_spend(user_id=user_id, project_id=project_id, actual_cost=0.048)
    # Next request of $0.005 would push total to $0.053 > $0.05
    ok, err = controller.check_budget_available(user_id=user_id, project_id=project_id, estimated_cost=0.005)
    assert ok is False
    assert "Daily project budget exceeded" in err


# ==============================================================================
# 8. Advanced Context-Safe Semantic Caching Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_semantic_cache_l1_and_l2_with_safety_invariants():
    cache = AdvancedSemanticCache(similarity_threshold=0.90)
    tenant_id = "org_cached"
    model = "mock-cheap"
    params = GenerationParameters()

    msg1 = [ChatMessage(role="user", content="How do I sort a list in Python?")]
    mock_resp = NormalizedCompletion(
        content="Use `list.sort()` or `sorted(list)`.",
        finish_reason="stop",
        provider="mock",
        model_alias=model,
        input_tokens=10,
        output_tokens=15,
        total_tokens=25,
        raw_usage_available=True,
    )

    # Store in cache
    await cache.set(tenant_id=tenant_id, model_alias=model, messages=msg1, parameters=params, completion=mock_resp)

    # 1. Exact match (L1 SHA-256)
    hit_resp, status = await cache.get(tenant_id=tenant_id, model_alias=model, messages=msg1, parameters=params)
    assert hit_resp is not None
    assert status == "hit_exact"
    assert hit_resp.content == mock_resp.content

    # 2. Context Safety: Negation change must NOT match semantic cache!
    # "How do I NOT sort a list in Python?" vs original
    negated_msg = [ChatMessage(role="user", content="How do I not sort a list in Python?")]
    miss_resp, status = await cache.get(tenant_id=tenant_id, model_alias=model, messages=negated_msg, parameters=params)
    assert miss_resp is None
    assert status == "miss"

    # 3. Tenant Isolation: Different tenant cannot access cache
    other_tenant_resp, status = await cache.get(
        tenant_id="different_org", model_alias=model, messages=msg1, parameters=params
    )
    assert other_tenant_resp is None
    assert status == "miss"


# ==============================================================================
# 9. Observability & OpenTelemetry Tracer Tests
# ==============================================================================
def test_opentelemetry_tracer_spans():
    tracer = ObservabilityTracer()
    trace_id = "tr_otel_test_123"

    span = tracer.start_span("gateway.pipeline", trace_id=trace_id, attributes={"tenant": "acme"})
    span.add_event("classifier_completed", {"category": "coding", "complexity": "MODERATE"})
    span.finish(status="OK")

    otel_dict = span.to_otel_dict()
    assert otel_dict["name"] == "gateway.pipeline"
    assert otel_dict["trace_id"] == trace_id
    assert otel_dict["status"]["code"] == "OK"
    assert len(otel_dict["events"]) == 1
    assert otel_dict["events"][0]["name"] == "classifier_completed"


# ==============================================================================
# 10. API Endpoints Integration Tests (Credentials, Budgets, Agentic, Bandit)
# ==============================================================================
@pytest.mark.asyncio
async def test_api_credentials_and_budgets_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Store BYOK Credential
        resp = await client.post(
            "/v1/credentials",
            json={"provider": "groq", "api_key": "gsk_test_secret_key_12345"},
            headers={"X-User-ID": "test_api_user"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "groq"
        assert "..." in data["masked_key"]

        # 2. List Credentials
        list_resp = await client.get("/v1/credentials", headers={"X-User-ID": "test_api_user"})
        assert list_resp.status_code == 200
        creds = list_resp.json()
        assert len(creds) >= 1
        assert any(c["provider"] == "groq" for c in creds)

        # 3. Configure Budget
        budget_resp = await client.post(
            "/v1/budgets",
            json={"project_id": "proj_beta", "max_cost_per_request": 0.05, "daily_budget": 5.0},
            headers={"X-User-ID": "test_api_user"},
        )
        assert budget_resp.status_code == 200
        b_data = budget_resp.json()
        assert b_data["status"] == "configured"
        assert b_data["budget"]["max_cost_per_request"] == 0.05

        # 4. Inspect Budget
        get_b_resp = await client.get("/v1/budgets/proj_beta", headers={"X-User-ID": "test_api_user"})
        assert get_b_resp.status_code == 200
        assert get_b_resp.json()["daily_budget"] == 5.0

        # 5. Inspect Bandit Stats
        bandit_resp = await client.get("/v1/routing/bandit-stats")
        assert bandit_resp.status_code == 200
        assert "exploration_rate" in bandit_resp.json()

        # 6. Reset Bandit Stats
        reset_resp = await client.post("/v1/routing/bandit-reset")
        assert reset_resp.status_code == 200
        assert reset_resp.json()["status"] == "reset"

        # 7. Agentic Planning Endpoint
        plan_resp = await client.post(
            "/v1/agentic/plan",
            json={
                "messages": [{"role": "user", "content": "Write a distributed raft consensus node in Python."}],
                "force_collaboration": True,
                "collaboration_strategy": "code_verification",
            },
        )
        assert plan_resp.status_code == 200
        plan_data = plan_resp.json()
        assert plan_data["mode"] == "collaborative"
        assert plan_data["total_steps"] == 2

        # 8. Delete Credential
        del_resp = await client.delete("/v1/credentials/groq", headers={"X-User-ID": "test_api_user"})
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "revoked"
