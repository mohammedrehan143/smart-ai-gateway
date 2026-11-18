"""Autonomous Agent Execution Engine for Smart AI CLI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from rich.panel import Panel
from rich.table import Table

from smart_ai_cli.client import AuthenticationError, GatewayClient, GatewayClientError
from smart_ai_cli.tools import AGENT_SYSTEM_PROMPT, TOOL_DEFINITIONS, execute_tool
from smart_ai_cli.ui import console, print_error, print_success


@dataclass
class AgentTaskResult:
    prompt: str
    steps_taken: int
    files_created: List[str] = field(default_factory=list)
    files_edited: List[str] = field(default_factory=list)
    files_read: List[str] = field(default_factory=list)
    commands_run: List[str] = field(default_factory=list)
    final_response: str = ""
    success: bool = True
    error: Optional[str] = None


def extract_action_blocks(content: str) -> List[Dict[str, Any]]:
    """Extracts fallback ```action:<tool_name>\n{...}``` codeblocks if model didn't use native tool_calls."""
    actions: List[Dict[str, Any]] = []
    pattern = r"```action:([a-zA-Z0-9_-]+)\s*\n([\s\S]*?)```"
    matches = re.finditer(pattern, content)
    for m in matches:
        tool_name = m.group(1).strip()
        raw_json = m.group(2).strip()
        try:
            args = json.loads(raw_json)
            actions.append({"name": tool_name, "args": args, "raw": m.group(0)})
        except json.JSONDecodeError:
            # Try fixing common json flaws or key=val
            actions.append({"name": tool_name, "args": {"raw_payload": raw_json}, "raw": m.group(0)})
    return actions


class AutonomousAgentRunner:
    """Orchestrates multi-step agent execution with real workspace tools."""

    def __init__(self, client: Optional[GatewayClient] = None, max_steps: int = 8):
        self.client = client or GatewayClient()
        self.max_steps = max_steps

    def execute_task(
        self,
        task_prompt: str,
        policy: str = "adaptive",
        temperature: float = 0.2,
        cwd: Optional[str] = None,
    ) -> AgentTaskResult:
        """Executes an autonomous task with tool execution loop."""
        work_dir = Path(cwd or ".").resolve()
        result = AgentTaskResult(prompt=task_prompt, steps_taken=0)

        console.print(
            Panel(
                f"[bold white]{task_prompt}[/]\n\n"
                f"[dim]Working Directory:[/] [cyan]{work_dir}[/]\n"
                f"[dim]Routing Policy:[/] [yellow]{policy}[/]",
                title="[bold cyan]● Autonomous Agent Task[/]",
                border_style="cyan",
            )
        )

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": task_prompt},
        ]

        step = 0
        while step < self.max_steps:
            step += 1
            result.steps_taken = step
            console.print(f"[dim]Step {step}/{self.max_steps} — Consulting Gateway models...[/dim]")

            try:
                resp = self.client.chat(
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    policy=policy,
                    temperature=temperature,
                )
            except AuthenticationError as exc:
                result.success = False
                result.error = str(exc)
                print_error(
                    f"Agent authentication failed: {exc}",
                    hint="Run 'smartai login --key <API_KEY>' or set GATEWAY_API_KEY to authenticate with the gateway.",
                )
                return result
            except GatewayClientError as exc:
                result.success = False
                result.error = str(exc)
                print_error(f"Agent inference failed: {exc}")
                return result
            except Exception as exc:
                result.success = False
                result.error = str(exc)
                print_error(f"Unexpected gateway error: {exc}")
                return result

            choices = resp.get("choices", [])
            if not choices:
                result.success = False
                result.error = "No choices in model response"
                return result

            choice = choices[0]
            choice_msg = choice.get("message", {})
            content = choice_msg.get("content") or ""
            native_tool_calls = choice_msg.get("tool_calls") or []

            # 1. Parse actions to execute (native tool_calls OR text action blocks)
            actions_to_run: List[Dict[str, Any]] = []

            if native_tool_calls:
                for tc in native_tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    raw_args = fn.get("arguments", "{}")
                    if isinstance(raw_args, str):
                        try:
                            parsed_args = json.loads(raw_args)
                        except Exception:
                            parsed_args = {}
                    else:
                        parsed_args = raw_args or {}
                    actions_to_run.append(
                        {
                            "id": tc.get("id"),
                            "name": fn_name,
                            "args": parsed_args,
                            "native": True,
                        }
                    )
            else:
                # Check for action blocks in content
                block_actions = extract_action_blocks(content)
                for ba in block_actions:
                    actions_to_run.append(
                        {
                            "id": None,
                            "name": ba["name"],
                            "args": ba["args"],
                            "native": False,
                            "raw": ba["raw"],
                        }
                    )

            # 2. If no actions were requested, agent has finished!
            if not actions_to_run:
                result.final_response = content
                if content.strip():
                    console.print(f"\n[bold green]Agent Response:[/]\n{content.strip()}\n")
                break

            # 3. Execute requested actions
            tool_outputs: List[Dict[str, Any]] = []
            for act in actions_to_run:
                name = act["name"]
                args = act["args"]

                args_preview = ", ".join(
                    f"{k}='{v}'" if not isinstance(v, str) or len(v) < 35 else f"{k}='{v[:32]}...'"
                    for k, v in args.items()
                )
                console.print(f"  [bold yellow]⚙ Action:[/] [cyan]{name}[/]({args_preview})")

                success, tool_res = execute_tool(name, args)

                if success:
                    console.print(f"  [bold green]✔[/] {tool_res}")
                    if name == "write_file":
                        result.files_created.append(args.get("path", ""))
                    elif name == "edit_file":
                        result.files_edited.append(args.get("path", ""))
                    elif name == "read_file":
                        result.files_read.append(args.get("path", ""))
                    elif name == "run_command":
                        result.commands_run.append(args.get("command", ""))
                else:
                    console.print(f"  [bold red]✖[/] {tool_res}")

                tool_outputs.append(
                    {
                        "call_id": act.get("id"),
                        "name": name,
                        "success": success,
                        "output": tool_res,
                        "native": act.get("native", False),
                    }
                )

            # 4. Feed tool outputs back into conversation history
            if native_tool_calls:
                # Append assistant message with tool_calls
                messages.append(
                    {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": native_tool_calls,
                    }
                )
                # Append tool messages
                for out in tool_outputs:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": out["call_id"] or "call_unknown",
                            "name": out["name"],
                            "content": out["output"],
                        }
                    )
            else:
                # Text-based action feedback
                messages.append({"role": "assistant", "content": content})
                feedback_lines = [f"Result of {out['name']}:\n{out['output']}" for out in tool_outputs]
                feedback_prompt = "\n\n".join(feedback_lines)
                feedback_prompt += "\n\nContinue with next actions or provide your final conclusion if finished."
                messages.append({"role": "user", "content": feedback_prompt})

        # Summary Display
        table = Table(title="Agent Task Summary", border_style="cyan")
        table.add_column("Category", style="bold white")
        table.add_column("Details", style="dim")

        table.add_row("Steps Executed", str(result.steps_taken))
        if result.files_created:
            table.add_row("Files Created", ", ".join(result.files_created))
        if result.files_edited:
            table.add_row("Files Edited", ", ".join(result.files_edited))
        if result.files_read:
            table.add_row("Files Read", ", ".join(result.files_read))
        if result.commands_run:
            table.add_row("Commands Run", ", ".join(result.commands_run))
        table.add_row("Outcome", "[bold green]Completed[/]" if result.success else "[bold red]Failed[/]")

        console.print(table)
        print_success("Agent finished task successfully!")
        return result
