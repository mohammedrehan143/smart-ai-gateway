"""Chat commands: smartai chat & smartai ask."""

from __future__ import annotations

import json
import re
import sys
from typing import Dict, List, Optional
import typer
from smart_ai_cli.agent_runner import AutonomousAgentRunner
from smart_ai_cli.auth import default_auth_manager
from smart_ai_cli.client import AuthenticationError, GatewayClient, GatewayClientError
from smart_ai_cli.config import default_config_manager
from smart_ai_cli.ui import (
    ChatPrompt,
    console,
    print_chat_header,
    print_chat_metadata,
    print_error,
)

app = typer.Typer(help="Interactive chat session and one-shot queries.")
CHAT_INDENT = "    "

ACTION_PROMPT_REGEX = re.compile(
    r"^(can you\s+)?(please\s+)?(create|make|write|edit|update|modify|read|list|delete|touch)\s+(a\s+|an\s+|the\s+)?([a-zA-Z0-9_\-]+\s+)?(file|folder|directory|script|code|[\w\-.]+\.[a-zA-Z0-9]+)\b",
    re.IGNORECASE,
)


@app.command("chat")
def chat_cmd(
    policy: Optional[str] = typer.Option(
        None, "--policy", "-p", help="Routing policy: adaptive, always_cheap, always_strong"
    ),
    temperature: Optional[float] = typer.Option(None, "--temperature", "-t", help="Sampling temperature (0.0 to 2.0)"),
    stream: Optional[bool] = typer.Option(None, "--stream/--no-stream", help="Enable or disable token streaming"),
) -> None:
    """Starts an interactive multi-turn terminal chat session with intelligent auto-routing."""
    cfg = default_config_manager.load_config()
    active_policy = policy or cfg.default_policy
    active_temp = temperature if temperature is not None else cfg.default_temperature
    use_stream = stream if stream is not None else cfg.stream_output

    client = GatewayClient()

    if not client.api_key:
        try:
            client.verify_auth()
        except AuthenticationError:
            is_interactive = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
            console.print(
                f"{CHAT_INDENT}[bold yellow]▲ Gateway requires authentication (no API key configured).[/bold yellow]"
            )
            if is_interactive:
                try:
                    entered = ChatPrompt.ask(
                        f"{CHAT_INDENT}[bold white]Enter Gateway API Key to authenticate[/bold white]"
                    ).strip()
                    if entered:
                        default_auth_manager.set_api_key(entered)
                        client.api_key = entered
                        console.print(f"{CHAT_INDENT}[bold green]✔[/bold green] Credentials saved successfully.\n")
                    else:
                        console.print(f"{CHAT_INDENT}[dim]Continuing unauthenticated...[/dim]\n")
                except (KeyboardInterrupt, EOFError):
                    return
            else:
                console.print(
                    f"{CHAT_INDENT}[dim]Hint: Run 'smartai login --key <API_KEY>' or set GATEWAY_API_KEY.[/dim]\n"
                )
        except Exception:
            pass

    print_chat_header(cfg.gateway_url, active_policy, active_temp)

    conversation: List[Dict[str, str]] = []

    while True:
        try:
            user_input = ChatPrompt.ask(f"\n{CHAT_INDENT}[bold cyan]❯[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n{CHAT_INDENT}[dim]Session ended.[/dim]")
            break

        if not user_input:
            continue

        # In-chat slash commands
        if user_input in ("/exit", "/quit", ":q"):
            console.print(f"{CHAT_INDENT}[dim]Exiting chat session. Goodbye![/dim]\n")
            break
        elif user_input in ("/reset", "/clear"):
            conversation.clear()
            console.print(f"{CHAT_INDENT}[bold green]✔[/bold green] Conversation history cleared.")
            continue
        elif user_input.startswith("/policy"):
            parts = user_input.split()
            valid_policies = (
                "adaptive",
                "always_cheap",
                "always_strong",
                "cost_optimized",
                "balanced",
                "quality_first",
                "performance_optimized",
            )
            if len(parts) > 1 and parts[1].lower() in valid_policies:
                active_policy = parts[1].lower()
                console.print(
                    f"{CHAT_INDENT}[bold green]✔[/bold green] Switched routing policy to: [bold yellow]{active_policy}[/]"
                )
            else:
                console.print(
                    f"{CHAT_INDENT}[bold yellow]▲[/bold yellow] Usage: /policy <adaptive | always_cheap | always_strong | cost_optimized | balanced | quality_first | performance_optimized>"
                )
            continue
        elif user_input == "/help":
            console.print(
                f"{CHAT_INDENT}[bold cyan]Available chat session commands:[/]\n"
                f"{CHAT_INDENT}  /exit, /quit      - Exit chat session\n"
                f"{CHAT_INDENT}  /reset, /clear    - Clear conversation history\n"
                f"{CHAT_INDENT}  /policy <name>    - Change policy (adaptive, always_cheap, always_strong)\n"
                f"{CHAT_INDENT}  /do <task>        - Run autonomous task (create/edit files, run commands)\n"
                f"{CHAT_INDENT}  /help             - Display this help message"
            )
            continue
        is_action_prompt = bool(ACTION_PROMPT_REGEX.match(user_input.strip()))
        if user_input.startswith("/do ") or user_input.startswith("/task ") or is_action_prompt:
            task_text = user_input
            if user_input.startswith("/do ") or user_input.startswith("/task "):
                task_text = user_input.split(" ", 1)[1].strip()
            if task_text:
                runner = AutonomousAgentRunner()
                runner.execute_task(task_text, policy=active_policy, temperature=active_temp)
                continue

        # Sanitize existing history to prevent corrupted or empty turns from lingering
        conversation[:] = [
            m for m in conversation
            if (m.get("content") or "").strip() or m.get("tool_calls")
        ]

        conversation.append({"role": "user", "content": user_input})

        try:
            if use_stream:
                full_reply = ""
                meta_chunk: Optional[Dict] = None

                with console.status(f"{CHAT_INDENT}[dim cyan]Thinking...[/dim cyan]", spinner="dots") as status:
                    stream_iter = client.stream_chat(conversation, policy=active_policy, temperature=active_temp)
                    first_chunk = None
                    for chunk in stream_iter:
                        first_chunk = chunk
                        break
                    status.stop()

                def write_stream_content(content: str) -> None:
                    for char in content:
                        if char == "\n":
                            sys.stdout.write(f"\n{CHAT_INDENT}")
                        else:
                            sys.stdout.write(char)
                    sys.stdout.flush()

                console.print()
                sys.stdout.write(CHAT_INDENT)

                if first_chunk:
                    choices = first_chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        delta_content = delta.get("content")
                        if delta_content:
                            write_stream_content(delta_content)
                            full_reply += delta_content
                    if "usage" in first_chunk or "routing" in first_chunk:
                        meta_chunk = first_chunk

                for chunk in stream_iter:
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        delta_content = delta.get("content")
                        if delta_content:
                            write_stream_content(delta_content)
                            full_reply += delta_content
                    if "usage" in chunk or "routing" in chunk:
                        meta_chunk = chunk

                sys.stdout.write("\n\n")
                sys.stdout.flush()

                if full_reply and full_reply.strip():
                    conversation.append({"role": "assistant", "content": full_reply})
                else:
                    if conversation and conversation[-1].get("role") == "user":
                        conversation.pop()

                if meta_chunk:
                    routing = meta_chunk.get("routing", {})
                    usage = meta_chunk.get("usage", {})
                    print_chat_metadata(
                        prompt=user_input,
                        model=meta_chunk.get("model", "unknown"),
                        tier=routing.get("tier", "unknown"),
                        policy=routing.get("policy", active_policy),
                        latency_ms=meta_chunk.get("latency_ms", 0),
                        tokens=usage.get("total_tokens", 0),
                        cost=usage.get("cost_estimate"),
                        cached=meta_chunk.get("cached", False),
                        trace_id=meta_chunk.get("trace_id"),
                        classification_level=routing.get("classification_level"),
                        reason=routing.get("reason"),
                        agent=routing.get("agent"),
                        provider=meta_chunk.get("provider") or routing.get("selected_provider"),
                        mock_mode=routing.get("mock_mode"),
                        input_tokens=usage.get("input_tokens"),
                        output_tokens=usage.get("output_tokens"),
                        indent=4,
                    )
            else:
                with console.status(f"{CHAT_INDENT}[dim cyan]Thinking...[/dim cyan]", spinner="dots"):
                    resp = client.chat(conversation, policy=active_policy, temperature=active_temp)

                console.print()
                reply_text = resp["choices"][0]["message"]["content"] or ""
                indented_lines = "\n".join(f"{CHAT_INDENT}{line}" for line in reply_text.splitlines())
                console.print(indented_lines)
                console.print()
                if reply_text and reply_text.strip():
                    conversation.append({"role": "assistant", "content": reply_text})
                else:
                    if conversation and conversation[-1].get("role") == "user":
                        conversation.pop()

                routing = resp.get("routing", {})
                usage = resp.get("usage", {})
                print_chat_metadata(
                    prompt=user_input,
                    model=resp.get("model", "unknown"),
                    tier=routing.get("tier", "unknown"),
                    policy=routing.get("policy", active_policy),
                    latency_ms=resp.get("latency_ms", 0),
                    tokens=usage.get("total_tokens", 0),
                    cost=usage.get("cost_estimate"),
                    cached=resp.get("cached", False),
                    trace_id=resp.get("trace_id"),
                    classification_level=routing.get("classification_level"),
                    reason=routing.get("reason"),
                    agent=routing.get("agent"),
                    provider=resp.get("provider") or routing.get("selected_provider"),
                    mock_mode=routing.get("mock_mode"),
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                    indent=4,
                )

        except AuthenticationError as exc:
            if conversation and conversation[-1].get("role") == "user":
                conversation.pop()
            sys.stdout.write("\n")
            console.print(f"{CHAT_INDENT}[bold red]✖[/bold red] Chat request failed: {exc}")
            console.print(
                f"{CHAT_INDENT}[bold yellow]▲ Hint:[/] Gateway authentication failed. "
                f"Run [bold cyan]'smartai login --key <YOUR_KEY>'[/bold cyan] or set [bold cyan]GATEWAY_API_KEY[/bold cyan]."
            )
            is_interactive = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
            if is_interactive:
                try:
                    retry_key = ChatPrompt.ask(
                        f"{CHAT_INDENT}[bold white]Enter Gateway API Key to update and retry[/bold white]"
                    ).strip()
                    if retry_key:
                        default_auth_manager.set_api_key(retry_key)
                        client.api_key = retry_key
                        console.print(f"{CHAT_INDENT}[bold green]✔[/bold green] Key updated. Please try your message again.")
                except (KeyboardInterrupt, EOFError):
                    break
        except GatewayClientError as exc:
            if conversation and conversation[-1].get("role") == "user":
                conversation.pop()
            sys.stdout.write("\n")
            console.print(f"{CHAT_INDENT}[bold red]✖[/bold red] Chat request failed: {exc}")
        except KeyboardInterrupt:
            if conversation and conversation[-1].get("role") == "user":
                conversation.pop()
            sys.stdout.write("\n")
            console.print(f"{CHAT_INDENT}[dim]Response cancelled by user.[/dim]")
        except Exception as exc:
            if conversation and conversation[-1].get("role") == "user":
                conversation.pop()
            sys.stdout.write("\n")
            console.print(f"{CHAT_INDENT}[bold red]✖[/bold red] Unexpected error: {exc}")


@app.command("ask")
def ask_cmd(
    prompt: str = typer.Argument(..., help="The query or prompt to ask"),
    policy: Optional[str] = typer.Option(
        None, "--policy", "-p", help="Routing policy (adaptive, always_cheap, always_strong)"
    ),
    temperature: Optional[float] = typer.Option(None, "--temperature", "-t", help="Sampling temperature"),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="Stream response tokens"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output raw JSON completion response"),
    agent_mode: bool = typer.Option(
        False, "--do", "--agent", "-a", help="Execute as an autonomous task (creates/edits files on disk)"
    ),
) -> None:
    """Executes a single one-shot query or autonomous task with intelligent auto-routing."""
    cfg = default_config_manager.load_config()
    active_policy = policy or cfg.default_policy
    active_temp = temperature if temperature is not None else cfg.default_temperature

    # Check if this is an autonomous file/task operation
    is_action_prompt = bool(ACTION_PROMPT_REGEX.match(prompt.strip()))
    if agent_mode or is_action_prompt:
        runner = AutonomousAgentRunner()
        res = runner.execute_task(
            task_prompt=prompt,
            policy=active_policy,
            temperature=active_temp,
        )
        if not res.success:
            raise typer.Exit(code=1)
        return

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
                    prompt=prompt,
                    model=meta_chunk.get("model", "unknown"),
                    tier=routing.get("tier", "unknown"),
                    policy=routing.get("policy", active_policy),
                    latency_ms=meta_chunk.get("latency_ms", 0),
                    tokens=usage.get("total_tokens", 0),
                    cost=usage.get("cost_estimate"),
                    cached=meta_chunk.get("cached", False),
                    trace_id=meta_chunk.get("trace_id"),
                    classification_level=routing.get("classification_level"),
                    reason=routing.get("reason"),
                    agent=routing.get("agent"),
                    provider=meta_chunk.get("provider") or routing.get("selected_provider"),
                    mock_mode=routing.get("mock_mode"),
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                )
        else:
            resp = client.chat(messages, policy=active_policy, temperature=active_temp)
            reply_text = resp["choices"][0]["message"]["content"]
            console.print(reply_text)

            routing = resp.get("routing", {})
            usage = resp.get("usage", {})
            print_chat_metadata(
                prompt=prompt,
                model=resp.get("model", "unknown"),
                tier=routing.get("tier", "unknown"),
                policy=routing.get("policy", active_policy),
                latency_ms=resp.get("latency_ms", 0),
                tokens=usage.get("total_tokens", 0),
                cost=usage.get("cost_estimate"),
                cached=resp.get("cached", False),
                trace_id=resp.get("trace_id"),
                classification_level=routing.get("classification_level"),
                reason=routing.get("reason"),
                agent=routing.get("agent"),
                provider=resp.get("provider") or routing.get("selected_provider"),
                mock_mode=routing.get("mock_mode"),
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
            )

    except AuthenticationError as exc:
        sys.stdout.write("\n")
        print_error(
            f"Authentication failed: {exc}",
            hint="Please run 'smartai login --key <API_KEY>' or configure GATEWAY_API_KEY in your environment or .env file.",
        )
        raise typer.Exit(code=1)
    except GatewayClientError as exc:
        sys.stdout.write("\n")
        print_error(f"Ask query failed: {exc}")
        raise typer.Exit(code=1)
