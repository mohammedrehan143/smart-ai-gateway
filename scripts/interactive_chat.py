"""Interactive Terminal Chat Client for Smart AI Gateway."""

import sys
import httpx

GATEWAY_URL = "http://localhost:8000/v1/chat"


def main():
    print("=" * 65)
    print(" Smart AI Gateway - Interactive Chat")
    print(" Gateway URL:", GATEWAY_URL)
    print(" Type 'exit' or 'quit' to close. Type '/policy <name>' to switch.")
    print(" Policies: adaptive (default), always_cheap, always_strong")
    print("=" * 65 + "\n")

    current_policy = "adaptive"
    messages = []

    client = httpx.Client(timeout=30.0)

    # Check connection
    try:
        health = client.get("http://localhost:8000/health/live")
        if health.status_code != 200:
            print("[WARN] Gateway health returned non-200. Is the server running?")
    except Exception:
        print("[ERROR] Could not connect to gateway at http://localhost:8000.")
        print("Please ensure the server is running in another terminal:")
        print("    uvicorn app.main:app --port 8000\n")
        return

    while True:
        try:
            user_input = input(f"\nYou [{current_policy}]> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting chat.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break

        if user_input.startswith("/policy"):
            parts = user_input.split()
            if len(parts) > 1 and parts[1] in ("adaptive", "always_cheap", "always_strong"):
                current_policy = parts[1]
                print(f"Policy switched to: {current_policy}")
            else:
                print("Usage: /policy <adaptive | always_cheap | always_strong>")
            continue

        messages.append({"role": "user", "content": user_input})

        payload = {
            "messages": messages,
            "routing": {"policy": current_policy},
            "parameters": {"temperature": 0.2, "max_output_tokens": 1024},
        }

        try:
            resp = client.post(GATEWAY_URL, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                assistant_msg = data["choices"][0]["message"]["content"]
                model = data.get("model", "unknown")
                routing = data.get("routing", {})
                tier = routing.get("tier", "unknown")
                reason = routing.get("reason", "")
                latency = data.get("latency_ms", 0)
                cached = data.get("cached", False)
                usage = data.get("usage", {})
                tokens = usage.get("total_tokens", 0)
                cost = usage.get("cost_estimate")
                cost_str = f"${cost:.6f}" if cost is not None else "N/A"

                print(f"\nGateway [{model} | {tier.upper()} | {latency}ms | {tokens} tokens | {cost_str} | cached={cached}]:")
                print(f"Reason: {reason}")
                print("-" * 50)
                print(assistant_msg)
                print("-" * 50)

                messages.append({"role": "assistant", "content": assistant_msg})
            else:
                print(f"[Error {resp.status_code}]: {resp.text}")
        except Exception as e:
            print(f"[Connection Error]: {e}")


if __name__ == "__main__":
    main()
