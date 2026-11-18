"""Sequential multi-turn regression test script for Smart AI Gateway."""
import urllib.request
import json
import sys

prompts = [
    "hi",
    "hy",
    "where to check benchmark",
    "What is Python?",
    "Explain recursion",
    "Design a scalable distributed multi-agent architecture"
]

conversation = []
print("=== SEQUENTIAL MULTI-TURN REGRESSION SESSION ===\n")

all_passed = True

for i, p in enumerate(prompts, 1):
    conversation.append({"role": "user", "content": p})
    req_body = {
        "messages": list(conversation),
        "routing": {"policy": "adaptive", "user_id": "default_user"},
        "parameters": {"temperature": 0.2, "max_output_tokens": 256}
    }
    req = urllib.request.Request(
        "http://localhost:8000/v1/chat",
        data=json.dumps(req_body).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        print(f"HTTP Error {err.code}: {err.read().decode('utf-8')}")
        sys.exit(1)

    choice = data["choices"][0]["message"]
    routing = data.get("routing", {})
    usage = data.get("usage", {})

    conversation.append({"role": "assistant", "content": choice["content"]})

    level = routing.get("classification_level")
    agent = routing.get("agent")
    tier = routing.get("tier")
    model = data.get("model")

    # Validation against requirements
    expected_agent = "Weak Agent" if i < 6 else "Strong Agent"
    expected_level = 1 if i < 6 else 3
    passed = (agent == expected_agent and level == expected_level)
    if not passed:
        all_passed = False
    status_symbol = "✔ PASS" if passed else "✖ FAIL"

    print(f"Turn {i}: Prompt: \"{p}\"  [{status_symbol}]")
    print(f"  Classification Level: {level}")
    print(f"  Reason: {routing.get('reason')}")
    print(f"  Selected Agent: {agent} (Tier: {tier})")
    print(f"  Provider: {data.get('provider') or routing.get('selected_provider')}")
    print(f"  Model: {model}")
    print(f"  Mock Mode: {routing.get('mock_mode')}")
    print(f"  Latency: {data.get('latency_ms')}ms")
    print(f"  Tokens: {usage.get('total_tokens')} (in: {usage.get('prompt_tokens')}, out: {usage.get('completion_tokens')})")
    print(f"  Cost: ${usage.get('cost_estimate')}")
    print(f"  Trace ID: {data.get('trace_id')}")
    print("-" * 70)

print(f"\nFinal Regression Result: {'ALL 6 PROMPTS PASSED!' if all_passed else 'REGRESSION FAILED!'}")
sys.exit(0 if all_passed else 1)
