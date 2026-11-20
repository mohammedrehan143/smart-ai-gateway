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


def clean_action_typos(text: str) -> str:
    """Fixes common CLI typing errors like 'login.htmla nd' -> 'login.html and'."""
    return re.sub(r"\.([a-zA-Z0-9]+)a\s*nd\b", r".\1 and", text, flags=re.IGNORECASE)


def is_action_prompt(text: str) -> bool:
    """Detects if a user query is an action/task command to create, modify, or save files on disk."""
    cleaned = clean_action_typos(text.strip())

    verbs = r"\b(?:create|make|write|build|generate|add|save|edit|update|modify|read|list|delete|touch)\b"
    targets = r"\b(?:file|folder|directory|script|code|page|webpage|component|app|template|[\w\-.]+\.(?:html?|py|js|ts|jsx|tsx|css|json|md|txt|ya?ml|sh|sql))\b"
    phrases = r"(?:in\s+this\s+(?:folder|directory)|name\s+(?:the\s+)?file\s+(?:as\s+)?|save\s+(?:it\s+)?(?:as|to|in)\s+|on\s+disk)"

    if re.search(verbs, cleaned, re.IGNORECASE) and (
        re.search(targets, cleaned, re.IGNORECASE) or re.search(phrases, cleaned, re.IGNORECASE)
    ):
        return True

    if ACTION_PROMPT_REGEX.match(cleaned):
        return True

    return False


def parse_mode_switch_intent(text: str) -> Optional[str]:
    """Detects natural language intent to switch agent or gateway mode.

    Handles phrasing like:
    - 'chage the strong agent to weak agent'
    - 'change the strong agent to weak agent'
    - 'switch to weak agent'
    - 'switch to auto'
    - 'switch to strong agent'
    - 'switch to expert mode'
    - 'use weak agent'
    - 'go to weak agent'
    - 'change agent to auto'
    """
    cleaned = text.strip().lower()
    if len(cleaned) > 120:
        return None

    # Check for action verbs: change, chage, switch, set, select, activate, use, go to, move to
    action_match = re.search(
        r"\b(?:chage|change|switch|set|select|turn\s+on|activate|use|move\s+to|go\s+to|go\s+back\s+to)\b",
        cleaned,
    )
    if not action_match:
        return None

    # Must specifically target agent or mode or tier
    agent_or_mode_mentioned = bool(
        re.search(r"\b(?:agent|mode|tier|model)\b", cleaned)
        or re.search(r"\b(?:weak|strong|expert|fast|cheap|auto|adaptive|balanced)\b", cleaned)
    )
    if not agent_or_mode_mentioned:
        return None

    # Target partition: if " to " is in prompt, take the destination
    target_text = cleaned
    if " to " in cleaned:
        target_text = cleaned.split(" to ", 1)[1]

    # Target: Weak / Fast / Cheap
    if re.search(r"\b(?:weak|cheap|fast)\b", target_text):
        return "fast"
    # Target: Strong
    if re.search(r"\b(?:strong)\b", target_text):
        return "strong"
    # Target: Expert
    if re.search(r"\b(?:expert)\b", target_text):
        return "expert"
    # Target: Auto / Adaptive / Balanced / Dynamic / Default
    if re.search(r"\b(?:auto|adaptive|balanced|dynamic|default)\b", target_text):
        return "auto"

    # If no ' to ' target matched, check entire input
    if re.search(r"\b(?:weak|cheap|fast)\b", cleaned):
        return "fast"
    if re.search(r"\b(?:expert)\b", cleaned):
        return "expert"
    if re.search(r"\b(?:strong)\b", cleaned):
        return "strong"
    if re.search(r"\b(?:auto|adaptive|balanced|dynamic|default)\b", cleaned):
        return "auto"

    return None


@app.command("chat")
def chat_cmd(
    policy: Optional[str] = typer.Option(
        None, "--policy", "-p", help="Routing policy: adaptive, always_cheap, always_strong"
    ),
    mode: Optional[str] = typer.Option(None, "--mode", "-m", help="Gateway mode: auto, fast, balanced, strong, expert"),
    temperature: Optional[float] = typer.Option(None, "--temperature", "-t", help="Sampling temperature (0.0 to 2.0)"),
    stream: Optional[bool] = typer.Option(None, "--stream/--no-stream", help="Enable or disable token streaming"),
) -> None:
    """Starts an interactive multi-turn terminal chat session with intelligent auto-routing."""
    cfg = default_config_manager.load_config()
    active_policy = policy or cfg.default_policy
    active_temp = temperature if temperature is not None else cfg.default_temperature
    use_stream = stream if stream is not None else cfg.stream_output

    # Mode defaults to auto for dynamic per-prompt routing unless explicitly specified
    active_mode = (mode or "auto").lower()
    if active_policy == "always_strong" and not mode:
        active_mode = "strong"
    elif active_policy == "always_cheap" and not mode:
        active_mode = "fast"

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

    agent_runner = AutonomousAgentRunner(client=client)

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
            active_mode = "auto"
            active_policy = "adaptive"
            try:
                client.set_session_mode("auto")
            except Exception:
                pass
            console.print(
                f"{CHAT_INDENT}[bold green]✔[/bold green] Conversation history cleared and mode reset to Auto."
            )
            continue
        elif user_input.startswith("/mode"):
            parts = user_input.split()
            valid_modes = ("auto", "fast", "balanced", "strong", "expert")
            if len(parts) > 1 and parts[1].lower() in valid_modes:
                chosen_mode = parts[1].lower()
                active_mode = chosen_mode
                if chosen_mode == "strong":
                    active_policy = "always_strong"
                elif chosen_mode in ("fast", "weak"):
                    active_policy = "always_cheap"
                else:
                    active_policy = "adaptive"
                try:
                    client.set_session_mode(active_mode)
                except Exception:
                    pass
                console.print(
                    f"{CHAT_INDENT}[bold green]✔[/bold green] Switched gateway mode to: [bold magenta]{chosen_mode.upper()}[/bold magenta] (policy: [yellow]{active_policy}[/yellow])"
                )
            else:
                console.print(
                    f"{CHAT_INDENT}[bold yellow]▲[/bold yellow] Usage: /mode <auto | fast | balanced | strong | expert> (Current mode: [bold cyan]{active_mode.upper()}[/bold cyan])"
                )
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
                f"{CHAT_INDENT}  /reset, /clear    - Clear conversation history and reset mode to Auto\n"
                f"{CHAT_INDENT}  /mode <name>      - Change mode (auto, fast, balanced, strong, expert)\n"
                f"{CHAT_INDENT}  /policy <name>    - Change policy (adaptive, always_cheap, always_strong)\n"
                f"{CHAT_INDENT}  /do <task>        - Run autonomous task (create/edit files, run commands)\n"
                f"{CHAT_INDENT}  /help             - Display this help message"
            )
            continue

        # Natural language agent and mode switching (e.g. "chage the strong agent to weak agent", "switch to weak agent", "switch to auto")
        switch_intent = parse_mode_switch_intent(user_input)
        if switch_intent:
            active_mode = switch_intent
            if active_mode in ("fast", "weak"):
                active_mode = "fast"
                active_policy = "always_cheap"
                desc = "Weak Agent (Fast mode - cost & speed optimized)"
            elif active_mode == "strong":
                active_policy = "always_strong"
                desc = "Strong Agent (Strong mode - high reasoning effort)"
            elif active_mode == "expert":
                active_policy = "always_strong"
                desc = "Expert Agent (Expert mode - maximum reasoning & verification)"
            else:
                active_mode = "auto"
                active_policy = "adaptive"
                desc = "Auto Mode (Dynamic intelligent routing per prompt)"

            try:
                client.set_session_mode(active_mode)
            except Exception:
                pass

            console.print(f"{CHAT_INDENT}[bold green]✔[/bold green] Switched to [bold magenta]{desc}[/bold magenta].")
            continue

        effective_prompt = clean_action_typos(user_input)
        if user_input.startswith("/do ") or user_input.startswith("/task "):
            effective_prompt = clean_action_typos(user_input.split(" ", 1)[1].strip())

        try:
            agent_runner.execute_interactive_turn(
                user_input=effective_prompt,
                conversation=conversation,
                policy=active_policy,
                mode=active_mode,
                temperature=active_temp,
                use_stream=use_stream,
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
                        console.print(
                            f"{CHAT_INDENT}[bold green]✔[/bold green] Key updated. Please try your message again."
                        )
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
    mode: Optional[str] = typer.Option(None, "--mode", "-m", help="Gateway mode: auto, fast, balanced, strong, expert"),
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
    active_mode = mode.lower() if mode else None

    # Check if this is an autonomous file/task operation
    effective_prompt = clean_action_typos(prompt.strip())
    is_action = agent_mode or is_action_prompt(effective_prompt)
    if is_action:
        runner = AutonomousAgentRunner()
        res = runner.execute_task(
            task_prompt=effective_prompt,
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
            resp = client.chat(messages, policy=active_policy, mode=active_mode, temperature=active_temp)
            console.print_json(json.dumps(resp))
            return

        if stream:
            full_reply = ""
            meta_chunk: Optional[Dict] = None

            for chunk in client.stream_chat(messages, policy=active_policy, mode=active_mode, temperature=active_temp):
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
