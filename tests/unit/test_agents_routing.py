"""Unit tests for multi-agent system: CredentialManager, IntelligentRouter, and ExecutionEngine."""

import pytest
from agents.credential_manager import CredentialManager
from agents.execution_engine import ExecutionEngine
from agents.provider_manager import ProviderManager, ProviderResponse
from agents.router import IntelligentRouter
from agents.strong_agent import StrongAgent
from agents.weak_agent import WeakAgent


def test_credential_manager_storage_and_masking():
    cm = CredentialManager()
    
    # Store weak agent key
    weak_cfg = cm.store_agent_config(
        user_id="user_123",
        agent_type="weak",
        provider="groq",
        api_key="gsk_1234567890abcdef1234567890",
        model_id="llama-3.1-8b-instant",
    )
    assert weak_cfg.masked_key.startswith("gsk...")
    assert weak_cfg.get_plaintext_key() == "gsk_1234567890abcdef1234567890"
    assert weak_cfg.is_enabled is True

    # Store strong agent key
    strong_cfg = cm.store_agent_config(
        user_id="user_123",
        agent_type="strong",
        provider="openai",
        api_key="sk-proj-abcdefghijklmnopqrstuvwxyz1234567890",
        model_id="gpt-4o",
    )
    assert strong_cfg.masked_key.startswith("sk-...")
    assert strong_cfg.get_plaintext_key() == "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"

    # User isolation check
    assert cm.get_agent_config("user_999", "weak") is None

    # Safe dict does not expose plaintext key
    safe_dict = strong_cfg.to_safe_dict()
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz" not in str(safe_dict)
    assert safe_dict["masked_key"].startswith("sk-...")

    # Listing configs
    listing = cm.list_agent_configs("user_123")
    assert listing["weak"] is not None
    assert listing["strong"] is not None
    assert listing["weak"]["provider"] == "groq"
    assert listing["strong"]["provider"] == "openai"


@pytest.mark.parametrize(
    "prompt,expected_agent,max_complexity",
    [
        ("What is Python?", "weak", 2),
        ("Explain variables in Java.", "weak", 2),
        ("Summarise this paragraph for me.", "weak", 2),
        ("Convert 10 kilometres to metres.", "weak", 2),
        ("Explain binary search with code.", "weak", 2),
        ("Build a basic React login form.", "weak", 2),
        ("Write a function to reverse a string in Python.", "weak", 2),
    ],
)
def test_router_selects_weak_agent_for_simple_and_routine_tasks(prompt, expected_agent, max_complexity):
    router = IntelligentRouter()
    decision = router.classify_and_route(prompt)
    assert decision.agent == expected_agent
    assert decision.complexity <= max_complexity
    assert decision.confidence >= 0.85
    assert len(decision.reason) > 5


@pytest.mark.parametrize(
    "prompt,expected_agent,min_complexity",
    [
        ("Design a scalable distributed system with high availability.", "strong", 4),
        ("Debug a multi-threaded application with race conditions and deadlocks.", "strong", 4),
        ("Architect a complete multi-agent AI platform with consensus mechanisms.", "strong", 4),
        ("Analyse a machine learning model suffering from overfitting and distribution shift.", "strong", 4),
        ("Implement a two-phase commit distributed banking protocol.", "strong", 4),
        ("Perform forensic analysis on a lateral movement security incident with zero-day exploit.", "strong", 5),
    ],
)
def test_router_selects_strong_agent_for_complex_and_expert_tasks(prompt, expected_agent, min_complexity):
    router = IntelligentRouter()
    decision = router.classify_and_route(prompt)
    assert decision.agent == expected_agent
    assert decision.complexity >= min_complexity
    assert decision.confidence >= 0.90
    assert len(decision.reason) > 5


def test_router_manual_override():
    router = IntelligentRouter()
    
    # Simple prompt forced to strong
    d_strong = router.classify_and_route("What is 2+2?", manual_agent="strong")
    assert d_strong.agent == "strong"
    assert "Manual user override" in d_strong.reason

    # Complex prompt forced to weak
    d_weak = router.classify_and_route("Design distributed consensus raft system", manual_agent="weak")
    assert d_weak.agent == "weak"
    assert "Manual user override" in d_weak.reason


@pytest.mark.asyncio
async def test_execution_engine_routing_and_fallback(monkeypatch):
    cm = CredentialManager()
    cm.store_agent_config("u1", "weak", "groq", "gsk_test_key", "llama-3.1-8b-instant")
    cm.store_agent_config("u1", "strong", "openai", "sk_test_key", "gpt-4o")

    router = IntelligentRouter()
    pm = ProviderManager()

    # Mock provider execute
    async def mock_execute(provider, api_key, model_id, messages, **kwargs):
        return ProviderResponse(
            content=f"Real answer from {provider} model {model_id}",
            prompt_tokens=15,
            completion_tokens=25,
            total_tokens=40,
            model=model_id,
            provider=provider,
            latency_ms=150,
        )

    monkeypatch.setattr(pm, "execute", mock_execute)

    weak = WeakAgent(credential_mgr=cm, provider_mgr=pm)
    strong = StrongAgent(credential_mgr=cm, provider_mgr=pm)
    engine = ExecutionEngine(router=router, weak_agent=weak, strong_agent=strong, credential_mgr=cm)

    # 1. Simple prompt execution routes to Weak Agent
    res_weak = await engine.execute_prompt(user_id="u1", prompt="What is Python?")
    assert res_weak.success is True
    assert res_weak.agent == "weak"
    assert res_weak.provider == "groq"
    assert "llama-3.1-8b-instant" in res_weak.model
    assert res_weak.cost > 0.0

    # 2. Complex prompt execution routes to Strong Agent
    res_strong = await engine.execute_prompt(
        user_id="u1",
        prompt="Design a scalable distributed architecture with consensus",
    )
    assert res_strong.success is True
    assert res_strong.agent == "strong"
    assert res_strong.provider == "openai"
    assert "gpt-4o" in res_strong.model

    # 3. Analytics verification
    overview = engine.get_analytics_overview()
    assert overview["total_requests"] == 2
    assert overview["weak_agent_requests"] == 1
    assert overview["strong_agent_requests"] == 1
    assert overview["cost_savings_pct"] > 0.0


@pytest.mark.asyncio
async def test_execution_engine_fallback_when_weak_fails(monkeypatch):
    cm = CredentialManager()
    cm.store_agent_config("u1", "weak", "groq", "gsk_test_key", "llama-3.1-8b-instant")
    cm.store_agent_config("u1", "strong", "openai", "sk_test_key", "gpt-4o")

    router = IntelligentRouter()
    pm = ProviderManager()

    # Weak agent fails (e.g. rate limit / connection error), strong agent succeeds
    async def mock_execute(provider, api_key, model_id, messages, **kwargs):
        if provider == "groq":
            raise RuntimeError("Groq upstream 429 rate limit exceeded")
        return ProviderResponse(
            content="Fallback answer generated by Strong Agent",
            prompt_tokens=20,
            completion_tokens=30,
            total_tokens=50,
            model=model_id,
            provider=provider,
            latency_ms=220,
        )

    monkeypatch.setattr(pm, "execute", mock_execute)

    weak = WeakAgent(credential_mgr=cm, provider_mgr=pm)
    strong = StrongAgent(credential_mgr=cm, provider_mgr=pm)
    engine = ExecutionEngine(router=router, weak_agent=weak, strong_agent=strong, credential_mgr=cm)

    # Prompt would normally route to weak, but weak fails so it falls back to strong
    res = await engine.execute_prompt(user_id="u1", prompt="What is Python?")
    assert res.success is True
    assert res.agent == "strong"
    assert res.routing["fallback_used"] is True
    assert "Groq upstream 429" in res.routing["fallback_reason"]
    assert "Fallback answer" in res.response
