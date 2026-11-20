"""Automated tests proving Strong Mode and Expert Mode override behavior,
routing priority, provider validation, transparency metadata, and agent orchestration.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from agents.credential_manager import CredentialManager
from agents.execution_engine import ExecutionEngine
from agents.provider_manager import ProviderManager
from agents.router import IntelligentRouter
from agents.strong_agent import StrongAgent
from agents.weak_agent import WeakAgent
from app.domain.entities import ChatMessage, RoutingOptions
from app.domain.modes import (
    GatewayMode,
    get_reasoning_effort_for_mode,
    is_expert_mode,
    is_strong_mode,
    normalize_gateway_mode,
    validate_provider_and_model,
)
from app.domain.router import DeterministicRouter
from app.main import app


# ==============================================================================
# 1. Mode Management & Normalization Tests
# ==============================================================================
def test_gateway_mode_normalization():
    assert normalize_gateway_mode("auto") == GatewayMode.AUTO
    assert normalize_gateway_mode("FAST") == GatewayMode.FAST
    assert normalize_gateway_mode("Balanced") == GatewayMode.BALANCED
    assert normalize_gateway_mode("strong") == GatewayMode.STRONG
    assert normalize_gateway_mode("EXPERT") == GatewayMode.EXPERT
    assert normalize_gateway_mode(None) == GatewayMode.AUTO
    assert normalize_gateway_mode("invalid_mode") == GatewayMode.AUTO
    assert normalize_gateway_mode("adaptive") == GatewayMode.AUTO
    assert normalize_gateway_mode("weak") == GatewayMode.FAST


def test_gateway_mode_helpers():
    assert is_strong_mode("strong") is True
    assert is_strong_mode("expert") is True
    assert is_strong_mode("auto") is False
    assert is_strong_mode("fast") is False

    assert is_expert_mode("expert") is True
    assert is_expert_mode("strong") is False

    assert get_reasoning_effort_for_mode("expert") == "high"
    assert get_reasoning_effort_for_mode("strong") == "high"
    assert get_reasoning_effort_for_mode("fast") == "none"
    assert get_reasoning_effort_for_mode("balanced") == "medium"
    assert get_reasoning_effort_for_mode("auto") == "medium"


def test_provider_and_model_validation():
    # Valid configurations
    assert validate_provider_and_model("openai", "gpt-4o")[0] is True
    assert validate_provider_and_model("groq", "llama-3.1-8b-instant")[0] is True
    assert validate_provider_and_model("mock", "mock-strong")[0] is True

    # Invalid configurations
    is_valid, err = validate_provider_and_model("unsupported_provider", "gpt-4o")
    assert is_valid is False
    assert "Unsupported provider" in err

    is_valid, err = validate_provider_and_model("openai", "non-existent-model-xyz")
    assert is_valid is False
    assert "Invalid or unsupported model" in err


def test_credential_manager_session_mode():
    cm = CredentialManager()
    user_id = "test_user_session_modes"

    # Default is auto
    assert cm.get_session_mode(user_id) == "auto"

    # Set strong mode
    cm.set_session_mode(user_id, "strong")
    assert cm.get_session_mode(user_id) == "strong"

    # Set expert mode
    cm.set_session_mode(user_id, "expert")
    assert cm.get_session_mode(user_id) == "expert"

    # Clear mode
    cm.clear_session_mode(user_id)
    assert cm.get_session_mode(user_id) == "auto"


# ==============================================================================
# 2. Routing Priority & Strong Mode Override Tests
# ==============================================================================
def test_strong_mode_never_routes_to_weak_agent_on_simple_prompts():
    """Strong Mode must bypass weak agent even for trivial queries."""
    router = IntelligentRouter()
    simple_prompts = [
        "Hello",
        "What is 2+2?",
        "Say yes",
        "Hi there",
        "Define apple in one word",
    ]

    for p in simple_prompts:
        decision = router.classify_and_route(p, mode="strong")
        assert decision.agent == "strong", f"Prompt '{p}' in strong mode routed to {decision.agent}"
        assert decision.selected_mode == "strong"
        assert decision.reasoning_effort == "high"
        assert "Strong Mode" in decision.routing_reason


def test_expert_mode_never_routes_to_weak_agent():
    """Expert Mode must always route to strong agent with maximum reasoning effort."""
    router = IntelligentRouter()
    decision = router.classify_and_route("Hello", mode="expert")
    assert decision.agent == "strong"
    assert decision.selected_mode == "expert"
    assert decision.complexity == 5
    assert decision.reasoning_effort == "high"
    assert "Expert Mode" in decision.routing_reason


def test_auto_mode_still_uses_complexity_classification():
    """Auto Mode routes simple prompts to weak agent and complex prompts to strong agent."""
    router = IntelligentRouter()

    # Simple prompt -> Weak agent
    simple_dec = router.classify_and_route("What is the capital of France?", mode="auto")
    assert simple_dec.agent == "weak"
    assert simple_dec.selected_mode == "auto"

    # Complex prompt -> Strong agent
    complex_prompt = (
        "Architect a distributed, fault-tolerant event sourcing system in Python and Go, "
        "providing formal mathematical proof of linearizability and consensus under Byzantine faults."
    )
    complex_dec = router.classify_and_route(complex_prompt, mode="auto")
    assert complex_dec.agent == "strong"
    assert complex_dec.selected_mode == "auto"


def test_prompt_instruction_never_determines_selected_mode():
    """The system must NEVER rely on magic prompt text to switch modes."""
    router = IntelligentRouter()
    prompt_with_activation = "SMART AI GATEWAY STRONG MODE ACTIVATION: What is 1 + 1?"

    # When mode="auto", the prompt text does not force Strong Mode
    decision_auto = router.classify_and_route(prompt_with_activation, mode="auto")
    assert decision_auto.agent == "weak"
    assert decision_auto.selected_mode == "auto"

    # When mode="strong" explicitly configured, it routes to Strong Mode
    decision_strong = router.classify_and_route(prompt_with_activation, mode="strong")
    assert decision_strong.agent == "strong"
    assert decision_strong.selected_mode == "strong"


def test_deterministic_router_mode_override():
    """DeterministicRouter in app.domain respects Strong and Expert modes."""
    router = DeterministicRouter()
    prompt = [ChatMessage(role="user", content="Hello")]
    options = RoutingOptions(mode="strong")

    decision = router.route(prompt, options=options)
    assert decision.selected_model_alias in [
        "mock-strong",
        "gpt-4o",
        "claude-3-5-sonnet",
        "deepseek-r1-distill-llama-70b",
    ]
    assert decision.selected_mode == "strong"
    assert decision.reasoning_effort == "high"


# ==============================================================================
# 3. Execution Engine & Provider Validation Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_execution_engine_strong_mode_execution():
    cm = CredentialManager()
    pm = ProviderManager()
    router = IntelligentRouter()
    engine = ExecutionEngine(
        router=router,
        credential_mgr=cm,
        weak_agent=WeakAgent(credential_mgr=cm, provider_mgr=pm),
        strong_agent=StrongAgent(credential_mgr=cm, provider_mgr=pm),
    )

    resp = await engine.execute_prompt(
        prompt="Simple greeting",
        user_id="user_test_engine",
        mode="strong",
    )

    assert resp.agent == "strong"
    assert resp.selected_mode == "strong"
    assert resp.reasoning_effort == "high"
    assert "strong" in resp.routing_reason.lower()
    assert resp.token_usage["total"] > 0
    assert resp.latency_ms >= 0


@pytest.mark.asyncio
async def test_execution_engine_expert_mode_execution():
    cm = CredentialManager()
    pm = ProviderManager()
    router = IntelligentRouter()
    engine = ExecutionEngine(
        router=router,
        credential_mgr=cm,
        weak_agent=WeakAgent(credential_mgr=cm, provider_mgr=pm),
        strong_agent=StrongAgent(credential_mgr=cm, provider_mgr=pm),
    )

    resp = await engine.execute_prompt(
        prompt="Simple test",
        user_id="user_test_engine",
        mode="expert",
    )

    assert resp.agent == "strong"
    assert resp.selected_mode == "expert"
    assert resp.reasoning_effort == "high"
    assert resp.classification_level == 5


@pytest.mark.asyncio
async def test_mock_provider_never_falsely_reported_as_real_api():
    """Mock models must be explicitly reported as provider='mock' and mock_mode=True."""
    cm = CredentialManager()
    pm = ProviderManager()
    router = IntelligentRouter()
    engine = ExecutionEngine(
        router=router,
        credential_mgr=cm,
        weak_agent=WeakAgent(credential_mgr=cm, provider_mgr=pm),
        strong_agent=StrongAgent(credential_mgr=cm, provider_mgr=pm),
    )

    resp = await engine.execute_prompt(
        prompt="Tell me a joke",
        user_id="user_unconfigured",
        mode="strong",
    )

    # In test environment without external API keys, mock-strong is used
    if resp.is_mock:
        assert resp.actual_provider == "mock", f"Expected 'mock' but got '{resp.actual_provider}'"
        assert resp.mock_mode is True
        assert resp.actual_provider != "openai"
        assert resp.actual_provider != "groq"
        assert resp.actual_provider != "anthropic"


@pytest.mark.asyncio
async def test_strong_mode_provider_failure_does_not_fall_back_to_weak():
    """When Strong Mode fails, it must raise or report the error, NEVER quietly fall back to Weak Agent."""
    cm = CredentialManager()
    pm = ProviderManager()

    # Store an invalid/broken credential for strong agent
    cm.store_agent_config(
        user_id="user_broken_strong",
        agent_type="strong",
        provider="unsupported_dummy_provider",
        api_key="bad_key",
        model_id="non-existent-model",
    )

    router = IntelligentRouter()
    engine = ExecutionEngine(
        router=router,
        credential_mgr=cm,
        weak_agent=WeakAgent(credential_mgr=cm, provider_mgr=pm),
        strong_agent=StrongAgent(credential_mgr=cm, provider_mgr=pm),
    )

    try:
        resp = await engine.execute_prompt(
            prompt="Plan a trip",
            user_id="user_broken_strong",
            mode="strong",
        )
        assert resp.agent == "strong"
        assert resp.success is False
        assert "strong" in resp.error.lower() or "unsupported" in resp.error.lower()
        assert resp.fallback_status == "prohibited_in_strong_mode"
    except Exception as exc:
        err_str = str(exc).lower()
        assert "strong model unavailable" in err_str or "unsupported provider" in err_str or "not configured" in err_str


# ==============================================================================
# 4. Strong Agent Orchestration Capabilities
# ==============================================================================
def test_strong_agent_orchestration_planning_and_verification():
    cm = CredentialManager()
    pm = ProviderManager()
    strong_agent = StrongAgent(credential_mgr=cm, provider_mgr=pm)

    # 1. Multi-step planning
    plan = strong_agent.plan_task(
        "Build a Python microservice with SQLite database, calculate the sum of 100 integers, and verify performance."
    )
    assert plan["total_steps"] >= 2
    steps = plan["steps"]
    assert any(
        "analysis" in s["title"].lower() or "decomposition" in s["title"].lower() or "code" in s["title"].lower()
        for s in steps
    )

    # 2. Local tool execution
    calc_res = strong_agent._execute_local_tool("calculator", {"expression": "25 * 4 + 10"})
    assert calc_res["ok"] is True
    assert calc_res["result"] == 110.0

    # 3. Code verification - Valid Python code
    valid_py = "def hello():\n    return 'world'\n"
    res_valid = strong_agent.verify_result("Write a hello function", valid_py)
    assert res_valid["verification_passed"] is True
    assert res_valid["syntax_valid"] is True

    # 4. Code verification - Invalid syntax Python code
    invalid_py = "def bad_code(:\n    return 'broken'\n"
    res_invalid = strong_agent.verify_result("Write broken code", invalid_py)
    assert res_invalid["verification_passed"] is False
    assert res_invalid["syntax_valid"] is False
    assert len(res_invalid["syntax_errors"]) > 0


# ==============================================================================
# 5. Transparency Metadata Completeness Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_gateway_response_transparency_metadata():
    """All 10 required transparency fields must be present and correctly populated."""
    cm = CredentialManager()
    pm = ProviderManager()
    router = IntelligentRouter()
    engine = ExecutionEngine(
        router=router,
        credential_mgr=cm,
        weak_agent=WeakAgent(credential_mgr=cm, provider_mgr=pm),
        strong_agent=StrongAgent(credential_mgr=cm, provider_mgr=pm),
    )

    resp = await engine.execute_prompt(
        prompt="Detailed analysis of sorting algorithms",
        user_id="user_transparency",
        mode="strong",
    )

    data = resp.to_dict()

    # 1. Selected mode
    assert data["selected_mode"] == "strong"
    # 2. Classification level
    assert isinstance(data["classification_level"], int)
    # 3. Routing reason
    assert isinstance(data["routing_reason"], str) and len(data["routing_reason"]) > 0
    # 4. Actual provider
    assert data["actual_provider"] in ["mock", "openai", "groq", "anthropic", "google"]
    # 5. Actual model
    assert isinstance(data["actual_model"], str) and len(data["actual_model"]) > 0
    # 6. Reasoning effort
    assert data["reasoning_effort"] == "high"
    # 7. Fallback status
    assert data["fallback_status"] in [
        "none",
        "mock_fallback",
        "downgraded_to_weak",
        "prohibited_in_strong_mode",
        "not_triggered",
    ]
    # 8. Latency
    assert data["latency_ms"] >= 0
    # 9. Token usage
    assert "prompt" in data["token_usage"]
    assert "completion" in data["token_usage"]
    assert "total" in data["token_usage"]
    # 10. Estimated cost
    assert data["estimated_cost"] >= 0.0


# ==============================================================================
# 6. API Endpoints & Session Mode Integration Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_api_session_mode_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Default mode check
        res = await client.get("/api/agents/mode", params={"user_id": "api_test_user"})
        assert res.status_code == 200
        assert res.json()["mode"] == "auto"

        # Update mode to strong
        res = await client.post(
            "/api/agents/mode",
            json={"mode": "strong", "user_id": "api_test_user"},
        )
        assert res.status_code == 200
        assert res.json()["mode"] == "strong"

        # Verify persisted mode
        res = await client.get("/api/agents/mode", params={"user_id": "api_test_user"})
        assert res.status_code == 200
        assert res.json()["mode"] == "strong"

        # Reset mode
        res = await client.post(
            "/api/agents/mode",
            json={"mode": "auto", "user_id": "api_test_user"},
        )
        assert res.status_code == 200
        assert res.json()["mode"] == "auto"


@pytest.mark.asyncio
async def test_api_gateway_execute_with_strong_mode():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "prompt": "Hello world",
            "mode": "strong",
        }
        headers = {"X-User-ID": "api_strong_exec_user"}
        res = await client.post("/api/gateway/execute", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data["agent"] == "strong"
        assert data["selected_mode"] == "strong"
        assert data["reasoning_effort"] == "high"
        assert data["fallback_status"] is not None
        assert data["actual_provider"] is not None
        assert data["actual_model"] is not None


@pytest.mark.asyncio
async def test_chat_completions_with_x_gateway_mode_header():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Hello simple prompt"}],
        }
        headers = {"X-Gateway-Mode": "strong"}
        res = await client.post("/v1/chat/completions", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert "routing" in data
        assert data["routing"]["selected_mode"] == "strong"
        assert data["routing"]["reasoning_effort"] == "high"
        assert (
            data["model"] in ["mock-strong", "gpt-4o", "claude-3-5-sonnet", "deepseek-r1-distill-llama-70b"]
            or data["routing"]["actual_model"] is not None
        )


# ==============================================================================
# 7. Multi-Turn Auto Mode Routing & Natural Language Switching Tests
# ==============================================================================
def test_auto_mode_subsequent_simple_prompts_route_to_weak():
    """In Auto mode, after a complex prompt, subsequent simple prompts route back to Weak Agent."""
    router = IntelligentRouter()

    # Step 1: Complex prompt routes to Strong Agent
    complex_prompt = (
        "Architect a distributed, fault-tolerant event sourcing system in Python and Go, "
        "providing formal mathematical proof of linearizability and consensus under Byzantine faults."
    )
    decision_1 = router.classify_and_route(prompt=complex_prompt, mode="auto")
    assert decision_1.agent == "strong"
    assert decision_1.complexity >= 4

    # Step 2: Multi-turn history with complex prompt, but current prompt is simple
    history = [
        {"role": "user", "content": complex_prompt},
        {"role": "assistant", "content": "Here is the architectural design for the traffic system..."},
    ]

    for simple_prompt in ["hello", "hy", "forget that", "thanks!"]:
        decision_simple = router.classify_and_route(
            prompt=simple_prompt,
            conversation_history=history,
            mode="auto",
        )
        assert decision_simple.agent == "weak", (
            f"Prompt '{simple_prompt}' should route to weak agent but routed to {decision_simple.agent}"
        )
        assert decision_simple.complexity <= 2


def test_natural_language_agent_switching_parser():
    """Tests natural language mode and agent switching intent recognition."""
    from smart_ai_cli.commands.chat import parse_mode_switch_intent

    # Weak / Fast intents
    assert parse_mode_switch_intent("chage the strong agent to weak agent") == "fast"
    assert parse_mode_switch_intent("change the strong agent to weak agent") == "fast"
    assert parse_mode_switch_intent("switch to weak agent") == "fast"
    assert parse_mode_switch_intent("switch to weak ai") == "fast"
    assert parse_mode_switch_intent("switch to weak") == "fast"
    assert parse_mode_switch_intent("use weak agent") == "fast"
    assert parse_mode_switch_intent("go to weak agent") == "fast"
    assert parse_mode_switch_intent("switch to fast mode") == "fast"

    # Strong / Expert intents
    assert parse_mode_switch_intent("switch to strong agent") == "strong"
    assert parse_mode_switch_intent("switch to strong ai") == "strong"
    assert parse_mode_switch_intent("change to strong agent") == "strong"
    assert parse_mode_switch_intent("use strong agent") == "strong"
    assert parse_mode_switch_intent("switch to expert mode") == "expert"

    # Auto / Adaptive intents
    assert parse_mode_switch_intent("switch to auto") == "auto"
    assert parse_mode_switch_intent("change to auto mode") == "auto"
    assert parse_mode_switch_intent("switch to adaptive") == "auto"

    # Normal queries that should NOT trigger a mode switch
    assert parse_mode_switch_intent("hello") is None
    assert parse_mode_switch_intent("can you write a function to switch two values in python?") is None
    assert parse_mode_switch_intent("please create a file named test.py") is None


def test_strong_agent_does_not_borrow_weak_groq_key():
    """DynamicProviderAdapter must NOT use GROQ_API_KEY when resolving strong tier models."""
    import os
    from app.providers.resolver import DynamicProviderAdapter
    from app.core.errors import ProviderAuthError

    adapter = DynamicProviderAdapter()

    # Save env
    old_groq = os.environ.get("GROQ_API_KEY")
    old_openai = os.environ.get("OPENAI_API_KEY")
    old_env = os.environ.get("APP_ENV")

    try:
        os.environ["GROQ_API_KEY"] = "gsk_prod_live_groq_key_9876543210"
        os.environ.pop("OPENAI_API_KEY", None)

        # Resolving weak model should succeed with Groq (default_user or unconfigured tenant)
        resolved_weak = adapter._resolve_adapter("llama-3.1-8b-instant", user_id="default_user")
        assert resolved_weak.provider_name == "groq"

        # Resolving strong model (gpt-4o) must NOT borrow Groq key; must raise ProviderAuthError
        with pytest.raises(ProviderAuthError) as exc_info:
            adapter._resolve_adapter("gpt-4o", user_id="default_user")
        assert "Strong Agent API key is not configured" in str(exc_info.value)

    finally:
        if old_groq is not None:
            os.environ["GROQ_API_KEY"] = old_groq
        else:
            os.environ.pop("GROQ_API_KEY", None)
        if old_openai is not None:
            os.environ["OPENAI_API_KEY"] = old_openai
        else:
            os.environ.pop("OPENAI_API_KEY", None)
        if old_env is not None:
            os.environ["APP_ENV"] = old_env
        else:
            os.environ.pop("APP_ENV", None)


@pytest.mark.asyncio
async def test_hello_routes_and_executes_via_weak_agent():
    """Trivial prompt 'hello' must route and execute via Weak Agent without falling back to Strong Agent."""
    from agents.execution_engine import ExecutionEngine
    from agents.credential_manager import CredentialManager
    from agents.provider_manager import ProviderManager
    from agents.router import IntelligentRouter
    from agents.weak_agent import WeakAgent
    from agents.strong_agent import StrongAgent

    cm = CredentialManager()
    cm.store_agent_config("user_hello_test", "weak", "mock", "mock_key", "mock-cheap")
    cm.store_agent_config("user_hello_test", "strong", "mock", "mock_key", "mock-strong")

    pm = ProviderManager()
    router = IntelligentRouter()
    engine = ExecutionEngine(
        router=router,
        credential_mgr=cm,
        weak_agent=WeakAgent(credential_mgr=cm, provider_mgr=pm),
        strong_agent=StrongAgent(credential_mgr=cm, provider_mgr=pm),
    )

    resp = await engine.execute_prompt(user_id="user_hello_test", prompt="hello", mode="auto")
    assert resp.agent == "weak"
    assert resp.success is True
    assert resp.routing["fallback_used"] is False
    assert resp.model == "mock-cheap"


@pytest.mark.asyncio
async def test_weak_agent_stream_prompt_produces_response():
    """Streaming in fast mode with weak agent must stream tokens and finish with done."""
    from agents.execution_engine import ExecutionEngine
    from agents.credential_manager import CredentialManager
    from agents.provider_manager import ProviderManager
    from agents.router import IntelligentRouter
    from agents.weak_agent import WeakAgent
    from agents.strong_agent import StrongAgent

    cm = CredentialManager()
    cm.store_agent_config("user_stream_fast", "weak", "mock", "mock_key", "mock-cheap")

    pm = ProviderManager()
    router = IntelligentRouter()
    engine = ExecutionEngine(
        router=router,
        credential_mgr=cm,
        weak_agent=WeakAgent(credential_mgr=cm, provider_mgr=pm),
        strong_agent=StrongAgent(credential_mgr=cm, provider_mgr=pm),
    )

    events = []
    async for chunk in engine.stream_prompt(user_id="user_stream_fast", prompt="hello", mode="fast"):
        events.append(chunk.strip())

    token_events = [e for e in events if '"type": "token"' in e]
    done_events = [e for e in events if '"type": "done"' in e]

    assert len(token_events) > 0, "Expected token stream events"
    assert len(done_events) == 1, "Expected single done event"
    assert "data: [DONE]" in events


@pytest.mark.asyncio
async def test_weak_agent_stream_unconfigured_in_fast_mode_yields_message(monkeypatch):
    """When weak agent is unconfigured in explicit fast mode, a readable message must be streamed, not dropped."""
    import uuid
    from unittest.mock import patch
    from agents.execution_engine import ExecutionEngine
    from agents.credential_manager import CredentialManager
    from agents.provider_manager import ProviderManager
    from agents.router import IntelligentRouter
    from agents.weak_agent import WeakAgent
    from agents.strong_agent import StrongAgent
    import app.providers.resolver as resolver

    monkeypatch.setattr(resolver, "is_mock_mode_explicitly_enabled", lambda: False)

    cm = CredentialManager()
    pm = ProviderManager()
    router = IntelligentRouter()
    engine = ExecutionEngine(
        router=router,
        credential_mgr=cm,
        weak_agent=WeakAgent(credential_mgr=cm, provider_mgr=pm),
        strong_agent=StrongAgent(credential_mgr=cm, provider_mgr=pm),
    )

    unconf_user = f"user_unconf_{uuid.uuid4().hex[:8]}"
    events = []
    async for chunk in engine.stream_prompt(user_id=unconf_user, prompt="hello", mode="fast"):
        events.append(chunk.strip())

    token_events = [e for e in events if '"type": "token"' in e]
    assert len(token_events) > 0
    assert "Weak Agent" in token_events[0]
    assert "data: [DONE]" in events

