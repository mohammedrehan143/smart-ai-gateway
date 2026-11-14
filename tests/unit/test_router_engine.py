"""Unit tests for deterministic routing policy rules."""

from app.domain.entities import ChatMessage, RoutingOptions
from app.domain.router import DeterministicRouter


def test_forced_policies():
    router = DeterministicRouter()
    msg = [ChatMessage(role="user", content="def add(a, b): return a + b")]

    # always_cheap overrides code complexity
    dec_cheap = router.route(msg, RoutingOptions(policy="always_cheap"))
    assert dec_cheap.tier == "cheap"
    assert dec_cheap.reason_code == "POLICY_FORCED_CHEAP"

    # always_strong forces strong tier
    simple_msg = [ChatMessage(role="user", content="Hello")]
    dec_strong = router.route(simple_msg, RoutingOptions(policy="always_strong"))
    assert dec_strong.tier == "strong"
    assert dec_strong.reason_code == "POLICY_FORCED_STRONG"


def test_adaptive_routing_decisions():
    router = DeterministicRouter(char_threshold=500)

    # 1. Simple short query -> cheap tier
    simple_msg = [ChatMessage(role="user", content="What is photosynthesis?")]
    dec_simple = router.route(simple_msg, RoutingOptions(policy="adaptive"))
    assert dec_simple.tier == "cheap"
    assert dec_simple.reason_code == "BASELINE_STANDARD_TASK"

    # 2. Code snippet -> strong tier
    code_msg = [ChatMessage(role="user", content="Debug this function:\n```python\ndef run(): pass\n```")]
    dec_code = router.route(code_msg, RoutingOptions(policy="adaptive"))
    assert dec_code.tier == "strong"
    assert dec_code.reason_code == "CODE_OR_DEBUGGING_DETECTED"

    # 3. Reasoning / comparison -> strong tier
    reasoning_msg = [ChatMessage(role="user", content="Compare the pros and cons of SQLite vs Postgres.")]
    dec_reason = router.route(reasoning_msg, RoutingOptions(policy="adaptive"))
    assert dec_reason.tier == "strong"
    assert dec_reason.reason_code == "COMPLEX_REASONING_OR_MULTISTEP"
