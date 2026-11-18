"""Comprehensive Product QA, Functional Verification, and Security Audit Runner."""

from __future__ import annotations

import asyncio
import os
import sys
import time

import httpx
from httpx import ASGITransport, AsyncClient

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.domain.classifier import ComplexityLevel
from app.domain.entities import ChatMessage, RoutingOptions
from app.domain.router import DeterministicRouter
from app.domain.byok import default_byok_manager
from agents.router import IntelligentRouter
from agents.provider_manager import ProviderManager
from app.main import app


async def test_section_a_routing():
    print("\n=======================================================")
    print(" [STAGE 3A] TESTING 15 MODEL ROUTING SCENARIOS")
    print("=======================================================")
    router_det = DeterministicRouter()
    router_agent = IntelligentRouter()
    options = RoutingOptions(policy="adaptive", preference="balanced")

    scenarios = [
        # (id, name, prompt, history, expected_tier, expected_comp)
        ("S01", "Simple greetings", "Hello, good morning! How are you?", [], "cheap", ComplexityLevel.SIMPLE),
        ("S02", "Basic factual questions", "What is Python?", [], "cheap", ComplexityLevel.SIMPLE),
        ("S03", "General knowledge", "Where is the Eiffel Tower located?", [], "cheap", ComplexityLevel.SIMPLE),
        ("S04", "Mathematical calculations", "Calculate 15 * 24 + 100.", [], "cheap", ComplexityLevel.MODERATE),
        (
            "S05",
            "Complex mathematical reasoning",
            "Calculate step-by-step the surface integral using Gauss divergence theorem and prove convergence rigorously.",
            [],
            "strong",
            ComplexityLevel.EXPERT,
        ),
        (
            "S06",
            "Basic programming questions",
            "Write a function to check if a string is a palindrome in Python.",
            [],
            "cheap",
            ComplexityLevel.MODERATE,
        ),
        (
            "S07",
            "Complex programming tasks",
            "Implement Paxos or Raft distributed consensus protocol from scratch with leader election and state machine replication.",
            [],
            "strong",
            ComplexityLevel.COMPLEX,
        ),
        (
            "S08",
            "Code debugging",
            "Debug this asynchronous Python deadlock with race condition: async with lock1: async with lock2: ...",
            [],
            "strong",
            ComplexityLevel.COMPLEX,
        ),
        (
            "S09",
            "Architecture design",
            "Design a scalable distributed microservices architecture with Kafka event sourcing and saga pattern.",
            [],
            "strong",
            ComplexityLevel.COMPLEX,
        ),
        (
            "S10",
            "Long-context analysis",
            "Analyze the complete organizational history and structural dynamics of the late Bronze Age collapse across maritime civilizations spanning Greece, Egypt, and Anatolia. Discuss the systemic trade disruptions, drought patterns, and military migrations over 500 years in exhaustive detail."
            * 3,
            [],
            "cheap",
            ComplexityLevel.MODERATE,
        ),
        (
            "S11",
            "Multi-step reasoning",
            "Step 1: analyze tradeoff between SQL and NoSQL. Step 2: compare replication. Step 3: recommend for high write throughput.",
            [],
            "cheap",
            ComplexityLevel.MODERATE,
        ),
        ("S12", "Ambiguous prompts", "maybe it depends? what could you clarify?", [], "cheap", ComplexityLevel.SIMPLE),
        ("S13", "Very short prompts", "Hi", [], "cheap", ComplexityLevel.SIMPLE),
        (
            "S14",
            "Very long prompts",
            ("Please summarize the following document: " + "Deep learning models require compute. " * 50),
            [],
            "cheap",
            ComplexityLevel.MODERATE,
        ),
        (
            "S15",
            "Follow-up question (Turn 2 after Complex Turn 1)",
            "Hi, thanks!",
            [
                {"role": "user", "content": "Design a complex distributed banking architecture with two-phase commit."},
                {"role": "assistant", "content": "Here is the 2PC design."},
            ],
            "cheap",
            ComplexityLevel.SIMPLE,
        ),
    ]

    results = []
    passed = 0
    failed = 0

    for s_id, s_name, prompt, history, exp_tier, exp_comp in scenarios:
        messages = [ChatMessage(role=h["role"], content=h["content"]) for h in history]
        messages.append(ChatMessage(role="user", content=prompt))

        dec_det = router_det.route(messages, options)
        dec_agent = router_agent.classify_and_route(prompt, conversation_history=history)

        tier_ok = dec_det.tier == exp_tier
        comp_ok = dec_det.complexity == exp_comp.value
        consistency_ok = dec_det.tier == ("cheap" if dec_agent.agent == "weak" else "strong")

        is_success = tier_ok and comp_ok and consistency_ok
        if is_success:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"

        print(
            f"[{status}] {s_id}: {s_name} -> tier={dec_det.tier} (exp={exp_tier}), comp={dec_det.complexity} (exp={exp_comp.value}), consistent={consistency_ok}"
        )
        if not is_success:
            print(
                f"       Details: prompt='{prompt[:60]}...' | reason='{dec_det.reason_message}' | agent_decision={dec_agent.agent}"
            )

        results.append(
            {
                "id": s_id,
                "name": s_name,
                "prompt": prompt[:80],
                "expected_tier": exp_tier,
                "actual_tier": dec_det.tier,
                "expected_comp": exp_comp.value,
                "actual_comp": dec_det.complexity,
                "consistent_cli": consistency_ok,
                "status": status,
            }
        )

    print(f"-> Routing Scenarios: {passed}/{len(scenarios)} Passed")
    return results


async def test_section_b_byok(client: AsyncClient):
    print("\n=======================================================")
    print(" [STAGE 3B] TESTING BYOK FUNCTIONALITY & ISOLATION")
    print("=======================================================")
    # 1. Add API key for Tenant A
    r_add = await client.post(
        "/v1/credentials",
        json={"provider": "groq", "api_key": "gsk_alice_key_999", "base_url": "https://api.groq.com/openai/v1"},
        headers={"X-User-ID": "alice"},
    )
    assert r_add.status_code == 201, f"Failed to add key: {r_add.text}"
    add_data = r_add.json()
    assert add_data["masked_key"].startswith("gsk...")
    print("[PASS] Tenant Alice added Groq API key (masked in response).")

    # 2. Verify Tenant B cannot see Alice's key
    r_bob = await client.get("/v1/credentials", headers={"X-User-ID": "bob"})
    assert r_bob.status_code == 200
    bob_creds = r_bob.json()
    assert len(bob_creds) == 0
    print("[PASS] Tenant Bob cannot see Alice's credential (Zero leakage).")

    # 3. Update key
    r_upd = await client.post(
        "/v1/credentials",
        json={"provider": "groq", "api_key": "gsk_alice_key_updated_888", "base_url": "https://api.groq.com/openai/v1"},
        headers={"X-User-ID": "alice"},
    )
    assert r_upd.status_code == 201
    assert default_byok_manager.get_plaintext_key("alice", "groq") == "gsk_alice_key_updated_888"
    print("[PASS] Tenant Alice updated Groq API key successfully.")

    # 4. Multi-provider test: Alice adds OpenAI key
    r_openai = await client.post(
        "/v1/credentials",
        json={"provider": "openai", "api_key": "sk-proj-alice-openai-777"},
        headers={"X-User-ID": "alice"},
    )
    assert r_openai.status_code == 201
    list_alice = await client.get("/v1/credentials", headers={"X-User-ID": "alice"})
    assert len(list_alice.json()) == 2
    print("[PASS] Multi-provider support verified: Alice has 2 distinct provider keys.")

    # 5. Delete credential
    r_del = await client.delete("/v1/credentials/groq", headers={"X-User-ID": "alice"})
    assert r_del.status_code == 200
    assert default_byok_manager.get_plaintext_key("alice", "groq") is None
    print("[PASS] Tenant Alice deleted Groq credential successfully.")

    # Cleanup
    await client.delete("/v1/credentials/openai", headers={"X-User-ID": "alice"})


async def test_section_c_provider_resiliency(client: AsyncClient):
    print("\n=======================================================")
    print(" [STAGE 3C & 3D] TESTING PROVIDER RESILIENCY & AGENTS")
    print("=======================================================")
    pm = ProviderManager()

    # Test error translations
    fake_resp_401 = httpx.Response(401, text='{"error": {"message": "Invalid auth token"}}')
    try:
        pm._handle_error_response(fake_resp_401, "groq")
    except Exception as exc:
        assert "Authentication failed" in str(exc)
        print(f"[PASS] 401 translated cleanly: {exc}")

    fake_resp_429 = httpx.Response(429, headers={"Retry-After": "3"}, text='{"error": {"message": "Rate limited"}}')
    try:
        pm._handle_error_response(fake_resp_429, "openai")
    except Exception as exc:
        assert hasattr(exc, "retry_after_s")
        assert exc.retry_after_s == 3.0
        print(f"[PASS] 429 translated cleanly with Retry-After: {exc.retry_after_s}s")

    fake_resp_503 = httpx.Response(503, text='{"error": "Service overloaded"}')
    try:
        pm._handle_error_response(fake_resp_503, "anthropic")
    except Exception as exc:
        assert "server error (503)" in str(exc)
        print(f"[PASS] 503 translated cleanly: {exc}")


async def test_section_e_api_suite(client: AsyncClient):
    print("\n=======================================================")
    print(" [STAGE 3E] TESTING REST API ENDPOINTS")
    print("=======================================================")
    # 1. Health
    r_live = await client.get("/health/live")
    assert r_live.status_code == 200 and r_live.json()["status"] == "live"
    print("[PASS] GET /health/live returned 200 live.")

    r_ready = await client.get("/health/ready")
    assert r_ready.status_code == 200 and r_ready.json()["status"] == "ready"
    print("[PASS] GET /health/ready returned 200 ready.")

    # 2. Metrics
    r_metrics = await client.get("/metrics")
    assert r_metrics.status_code == 200
    print("[PASS] GET /metrics returned 200.")

    # 3. Models
    r_models = await client.get("/v1/models")
    assert r_models.status_code == 200 and len(r_models.json()["data"]) >= 4
    print(f"[PASS] GET /v1/models returned {len(r_models.json()['data'])} registered models.")

    # 4. Agentic plan
    r_plan = await client.post(
        "/v1/agentic/plan",
        json={"messages": [{"role": "user", "content": "Write a python script to calculate fibonacci"}]},
    )
    assert r_plan.status_code == 200
    plan_data = r_plan.json()
    assert plan_data["task_category"] == "coding"
    print(f"[PASS] POST /v1/agentic/plan returned mode={plan_data['mode']}, task={plan_data['task_category']}.")

    # 5. Chat completion with trace persistence
    r_chat = await client.post(
        "/v1/chat",
        json={
            "messages": [{"role": "user", "content": "What is Python?"}],
            "routing": {"policy": "adaptive"},
        },
    )
    assert r_chat.status_code == 200
    chat_resp = r_chat.json()
    assert chat_resp["routing"]["tier"] == "cheap"
    assert chat_resp["trace_id"]
    print(f"[PASS] POST /v1/chat succeeded with tier={chat_resp['routing']['tier']}, trace_id={chat_resp['trace_id']}.")

    # 6. Payload size limit (>1MB payload rejection)
    huge_text = "A" * (1024 * 1024 + 100)
    r_huge = await client.post(
        "/v1/chat",
        content=huge_text,
        headers={"Content-Type": "application/json", "Content-Length": str(len(huge_text))},
    )
    assert r_huge.status_code == 413
    print("[PASS] 413 Payload Too Large enforced for requests > 1MB.")


async def test_section_g_performance(client: AsyncClient):
    print("\n=======================================================")
    print(" [STAGE 3G] TESTING CONCURRENCY & LATENCY")
    print("=======================================================")
    # Concurrency test: 30 parallel requests
    start = time.time()
    tasks = [
        client.post(
            "/v1/chat",
            json={
                "messages": [{"role": "user", "content": f"Concurrency probe #{i}"}],
                "routing": {"policy": "always_cheap"},
            },
        )
        for i in range(30)
    ]
    responses = await asyncio.gather(*tasks)
    elapsed = time.time() - start
    assert all(r.status_code == 200 for r in responses)
    rps = len(responses) / elapsed
    print(f"[PASS] 30 Concurrent Requests: Elapsed={elapsed:.2f}s | Throughput={rps:.1f} req/s | Success=100%")


async def main():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await test_section_a_routing()
        await test_section_b_byok(client)
        await test_section_c_provider_resiliency(client)
        await test_section_e_api_suite(client)
        await test_section_g_performance(client)
    print("\nAll functional QA tests executed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
