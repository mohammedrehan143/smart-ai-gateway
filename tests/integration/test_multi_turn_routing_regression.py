"""Multi-turn sequential routing regression tests verifying context isolation."""

import pytest
from httpx import AsyncClient
from app.domain.classifier import ComplexityClassifier, ComplexityLevel
from app.domain.entities import ChatMessage, RoutingOptions
from app.domain.router import DeterministicRouter


@pytest.mark.parametrize(
    "history,latest_prompt,expected_complexity,expected_tier",
    [
        # 1. Complex request followed by a simple request
        (
            [
                {
                    "role": "user",
                    "content": "Design a complex distributed multi-agent architecture with Byzantine fault tolerance.",
                },
                {
                    "role": "assistant",
                    "content": "Here is the distributed architecture using PBFT and vector clocks...",
                },
            ],
            "Hi.",
            ComplexityLevel.SIMPLE,
            "cheap",
        ),
        # 2. Simple request followed by a complex request
        (
            [
                {"role": "user", "content": "Hello there"},
                {"role": "assistant", "content": "Hello! How can I assist you today?"},
            ],
            "Design a scalable distributed banking architecture with two-phase commit.",
            ComplexityLevel.COMPLEX,
            "strong",
        ),
        # 3. Coding request followed by casual conversation
        (
            [
                {
                    "role": "user",
                    "content": "Debug this complex asynchronous Python application suffering from deadlocks and race conditions.",
                },
                {
                    "role": "assistant",
                    "content": "The deadlock is caused by inverted lock acquisition on lines 42 and 58.",
                },
            ],
            "Thanks, what is the meaning of life?",
            ComplexityLevel.SIMPLE,
            "cheap",
        ),
        # 4. Long conversation with a simple latest request
        (
            [
                {"role": "user", "content": "Analyze CVE-2024-9999 lateral movement zero-day exploit."},
                {"role": "assistant", "content": "Exploit analysis complete."},
                {"role": "user", "content": "Implement two-phase commit distributed protocol."},
                {"role": "assistant", "content": "2PC protocol code generated."},
                {"role": "user", "content": "Audit kernel memory leak and heap dump."},
                {"role": "assistant", "content": "Heap dump analysis shows leaked slab caches."},
            ],
            "Good morning!",
            ComplexityLevel.SIMPLE,
            "cheap",
        ),
        # 5. Complex question followed by another simple query
        (
            [
                {
                    "role": "user",
                    "content": "Design a high-throughput microservices architecture with Kafka and event sourcing.",
                },
                {"role": "assistant", "content": "Architecture plan provided."},
            ],
            "What is Python?",
            ComplexityLevel.SIMPLE,
            "cheap",
        ),
    ],
)
def test_multi_turn_history_does_not_inflate_latest_complexity(
    history, latest_prompt, expected_complexity, expected_tier
):
    """Verifies that previous conversation history does NOT contaminate the latest request classification."""
    router = DeterministicRouter()
    messages = [ChatMessage(role=m["role"], content=m["content"]) for m in history]
    messages.append(ChatMessage(role="user", content=latest_prompt))

    # 1. Classification check
    classification = ComplexityClassifier.classify(messages)
    assert classification.complexity == expected_complexity, (
        f"Expected {expected_complexity.value} for prompt '{latest_prompt}', but got {classification.complexity.value}. Reason: {classification.reason}"
    )

    # 2. Router decision check
    decision = router.route(messages, RoutingOptions(policy="adaptive", preference="balanced"))
    assert decision.complexity == expected_complexity.value
    assert decision.tier == expected_tier, (
        f"Expected tier {expected_tier} for prompt '{latest_prompt}', but got {decision.tier} ({decision.selected_model_alias})"
    )


@pytest.mark.asyncio
async def test_sequential_conversations_api_e2e(async_client: AsyncClient):
    """E2E API test: Turn 1 is Complex (routed to strong), Turn 2 is 'Hi' (MUST route to cheap/weak)."""
    # Turn 1: Complex request
    conversation = [
        {"role": "user", "content": "Design a scalable distributed banking architecture with two-phase commit."}
    ]
    resp1 = await async_client.post(
        "/v1/chat",
        json={"messages": conversation, "routing": {"policy": "adaptive"}},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["routing"]["tier"] == "strong"
    assert data1["routing"]["complexity"] == "COMPLEX"

    # Turn 2: Assistant response + Simple "Hi"
    conversation.append({"role": "assistant", "content": data1["choices"][0]["message"]["content"]})
    conversation.append({"role": "user", "content": "Hi"})

    resp2 = await async_client.post(
        "/v1/chat",
        json={"messages": conversation, "routing": {"policy": "adaptive"}},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()

    # CRITICAL INVARIANT: Turn 2 MUST be cheap tier and SIMPLE complexity
    assert data2["routing"]["tier"] == "cheap", (
        f"Regression bug! Turn 2 'Hi' was routed to '{data2['routing']['tier']}' instead of cheap!"
    )
    assert data2["routing"]["complexity"] == "SIMPLE", (
        f"Regression bug! Turn 2 'Hi' had complexity '{data2['routing']['complexity']}' instead of SIMPLE!"
    )
