"""Chat commands: smartai chat & smartai ask."""

from __future__ import annotations

import json
import sys
from typing import Dict, List, Optional
import typer
from rich.prompt import Prompt
from smart_ai_cli.client import GatewayClient, GatewayClientError
from smart_ai_cli.config import default_config_manager
from smart_ai_cli.ui import (
    console,
    print_banner,
    print_chat_metadata,
    print_error,
    print_success,
    print_warning,
)

app = typer.Typer(help="Interactive chat session and one-shot queries.")


@app.command("chat")
def chat_cmd(
    policy: Optional[str] = typer.Option(None, "--policy", "-p", help="Routing policy: adaptive, always_cheap, always_strong"),
    temperature: Optional[float] = typer.Option(None, "--temperature", "-t", help="Sampling temperature (0.0 to 2.0)"),
    stream: Optional[bool] = typer.Option(None, "--stream/--no-stream", help="Enable or disable token streaming"),
) -> None:
    """Starts an interactive multi-turn terminal chat session with intelligent auto-routing."""
    cfg = default_config_manager.load_config()
    active_policy = policy or cfg.default_policy
    active_temp = temperature if temperature is not None else cfg.default_temperature
    use_stream = stream if stream is not None else cfg.stream_output

    client = GatewayClient()

    print_banner()
    console.print(f"[bold cyan]Connected to:[/] {cfg.gateway_url}")
    console.print(f"[bold yellow]Active Policy:[/] {active_policy} • [bold white]Temperature:[/] {active_temp}")
    console.print("[dim]Type your message, or enter /help, /reset, /policy, /exit[/dim]\n")

    conversation: List[Dict[str, str]] = []

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]You[/bold green]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session ended.[/dim]")
            break

        if not user_input:
            continue

        # In-chat slash commands
        if user_input in ("/exit", "/quit", ":q"):
            console.print("[dim]Exiting chat session. Goodbye![/dim]")
            break
        elif user_input in ("/reset", "/clear"):
            conversation.clear()
            print_success("Conversation history cleared.")
            continue
        elif user_input.startswith("/policy"):
            parts = user_input.split()
            if len(parts) > 1 and parts[1] in ("adaptive", "always_cheap", "always_strong"):
                active_policy = parts[1]
                print_success(f"Switched routing policy to: [bold yellow]{active_policy}[/]")
            else:
                print_warning("Usage: /policy <adaptive | always_cheap | always_strong>")
            continue
        elif user_input == "/help":
            console.print(
                "[bold cyan]Available chat session commands:[/]\n"
                "  /exit, /quit      - Exit chat session\n"
                "  /reset, /clear    - Clear conversation history\n"
                "  /policy <name>    - Change policy (adaptive, always_cheap, always_strong)\n"
                "  /help             - Display this help message"
            )
            continue

        conversation.append({"role": "user", "content": user_input})
        console.print("[bold cyan]Assistant:[/bold cyan] ", end="")

        try:
            if use_stream:
                full_reply = ""
                meta_chunk: Optional[Dict] = None

                for chunk in client.stream_chat(conversation, policy=active_policy, temperature=active_temp):
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        delta_content = delta.get("content")
                        if delta_content:
                            sys.stdout.write(delta_content)
                            sys.stdout.flush()
                            full_reply += delta_content
                    # Capture final chunk with usage & routing
                    if "usage" in chunk or "routing" in chunk:
                        meta_chunk = chunk

                sys.stdout.write("\n")
                sys.stdout.flush()

                conversation.append({"role": "assistant", "content": full_reply})

                if meta_chunk:
                    routing = meta_chunk.get("routing", {})
                    usage = meta_chunk.get("usage", {})
                    print_chat_metadata(
                        model=meta_chunk.get("model", "unknown"),
                        tier=routing.get("tier", "unknown"),
                        policy=routing.get("policy", active_policy),
                        latency_ms=meta_chunk.get("latency_ms", 0),
                        tokens=usage.get("total_tokens", 0),
                        cost=usage.get("cost_estimate"),
                        cached=meta_chunk.get("cached", False),
                        trace_id=meta_chunk.get("trace_id"),
                    )
            else:
                resp = client.chat(conversation, policy=active_policy, temperature=active_temp)
                reply_text = resp["choices"][0]["message"]["content"]
                console.print(reply_text)
                conversation.append({"role": "assistant", "content": reply_text})

                routing = resp.get("routing", {})
                usage = resp.get("usage", {})
                print_chat_metadata(
                    model=resp.get("model", "unknown"),
                    tier=routing.get("tier", "unknown"),
                    policy=routing.get("policy", active_policy),
                    latency_ms=resp.get("latency_ms", 0),
                    tokens=usage.get("total_tokens", 0),
                    cost=usage.get("cost_estimate"),
                    cached=resp.get("cached", False),
                    trace_id=resp.get("trace_id"),
                )

        except GatewayClientError as exc:
            sys.stdout.write("\n")
            print_error(f"Chat request failed: {exc}")
        except Exception as exc:
            sys.stdout.write("\n")
            print_error(f"Unexpected error: {exc}")


@app.command("ask")
def ask_cmd(
    prompt: str = typer.Argument(..., help="The query or prompt to ask"),
    policy: Optional[str] = typer.Option(None, "--policy", "-p", help="Routing policy (adaptive, always_cheap, always_strong)"),
    temperature: Optional[float] = typer.Option(None, "--temperature", "-t", help="Sampling temperature"),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="Stream response tokens"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output raw JSON completion response"),
) -> None:
    """Executes a single one-shot query with intelligent auto-routing."""
    cfg = default_config_manager.load_config()
    active_policy = policy or cfg.default_policy
    active_temp = temperature if temperature is not None else cfg.default_temperature

    client = GatewayClient()
    messages = [{"role": "user", "content": prompt}]

    try:
        if json_output:
            resp = client.chat(messages, policy=active_policy, temperature=active_temp)
            console.print_json(json.dumps(resp))
            return

        if stream:
            full_reply = ""
            meta_chunk: Optional[Dict] = None

            for chunk in client.stream_chat(messages, policy=active_policy, temperature=active_temp):
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    delta_content = delta.get("content")
                    if delta_content:
                        sys.stdout.write(delta_content)
                        sys.stdout.flush()
                        full_reply += delta_content
                if "usage" in chunk or "routing" in chunk:
                    meta_chunk = chunk

            sys.stdout.write("\n")
            sys.stdout.flush()

            if meta_chunk:
                routing = meta_chunk.get("routing", {})
                usage = meta_chunk.get("usage", {})
                print_chat_metadata(
                    model=meta_chunk.get("model", "unknown"),
                    tier=routing.get("tier", "unknown"),
                    policy=routing.get("policy", active_policy),
                    latency_ms=meta_chunk.get("latency_ms", 0),
                    tokens=usage.get("total_tokens", 0),
                    cost=usage.get("cost_estimate"),
                    cached=meta_chunk.get("cached", False),
                    trace_id=meta_chunk.get("trace_id"),
                )
        else:
            resp = client.chat(messages, policy=active_policy, temperature=active_temp)
            reply_text = resp["choices"][0]["message"]["content"]
            console.print(reply_text)

            routing = resp.get("routing", {})
            usage = resp.get("usage", {})
            print_chat_metadata(
                model=resp.get("model", "unknown"),
                tier=routing.get("tier", "unknown"),
                policy=routing.get("policy", active_policy),
                latency_ms=resp.get("latency_ms", 0),
                tokens=usage.get("total_tokens", 0),
                cost=usage.get("cost_estimate"),
                cached=resp.get("cached", False),
                trace_id=resp.get("trace_id"),
            )

    except GatewayClientError as exc:
        sys.stdout.write("\n")
        print_error(f"Ask query failed: {exc}")
        raise typer.Exit(code=1)
