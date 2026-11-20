"""Autonomous Agent Execution Engine for Smart AI CLI."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from rich.panel import Panel
from rich.table import Table

from smart_ai_cli.client import AuthenticationError, GatewayClient, GatewayClientError
from smart_ai_cli.tools import AGENT_SYSTEM_PROMPT, TOOL_DEFINITIONS, execute_tool
from smart_ai_cli.ui import console, print_chat_metadata, print_error, print_success


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


def clean_typos(text: str) -> str:
    """Fixes common CLI typing errors like 'login.htmla nd' -> 'login.html and'."""
    return re.sub(r"\.([a-zA-Z0-9]+)a\s*nd\b", r".\1 and", text, flags=re.IGNORECASE)


def extract_target_filename(prompt: Optional[str], content: str) -> Optional[str]:
    """Extracts target filename from task prompt, model text, or file mentions."""
    search_texts: List[str] = []
    if prompt:
        search_texts.append(clean_typos(prompt))
    search_texts.append(content)

    filename_patterns = [
        # name the file as login.html / name the file login.html / named as login.html / File: login.html
        r"(?:name\s+(?:the\s+)?file\s+(?:as\s+)?|named\s+(?:as\s+)?|filename\s*[:=]\s*|save\s+(?:it\s+)?(?:as|to|in)\s+|file\s*:\s*)[\*`\'\"]*([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)[\*`\'\"]*",
        # file named login.html / file called login.html
        r"file\s+(?:named|called)\s+[\*`\'\"]*([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)[\*`\'\"]*",
        # **login.html** file / `login.html` file
        r"[\*`\'\"]*([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)[\*`\'\"]*\s+file",
        # create / make / write / save login.html
        r"\b(?:create|make|write|touch|save)\s+[\*`\'\"]*([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)[\*`\'\"]*",
        # Markdown bold / backtick filename
        r"[\*`\'\"]([a-zA-Z0-9_\-./\\]+\.(?:html?|py|js|ts|jsx|tsx|css|json|md|txt|ya?ml|sh|sql))[\*`\'\"]",
        # Specific known extensions mentioned in text
        r"\b([a-zA-Z0-9_\-]+\.(?:html?|py|js|ts|jsx|tsx|css|json|md|txt|ya?ml|sh|sql))\b",
    ]

    for text in search_texts:
        for pat in filename_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                fn = m.group(1).strip().strip("`*'\"").rstrip(".,;:)")
                if fn and "." in fn and not fn.endswith("."):
                    return fn

    # Default heuristic based on prompt content
    if prompt:
        p_lower = prompt.lower()
        if "login" in p_lower and ("page" in p_lower or "html" in p_lower):
            return "login.html"

    return None


def extract_action_blocks(content: str, task_prompt: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extracts action codeblocks or synthesizes actions from code blocks and task prompt."""
    actions: List[Dict[str, Any]] = []

    # 1. Standard ```action:<tool_name>\n{...}``` or ```tool:<tool_name>\n{...}```
    pattern = r"```(?:action|tool):([a-zA-Z0-9_-]+)\s*\n([\s\S]*?)(?:```|$)"
    matches = re.finditer(pattern, content)
    for m in matches:
        tool_name = m.group(1).strip()
        raw_json = m.group(2).strip()
        try:
            args = json.loads(raw_json)
            actions.append({"name": tool_name, "args": args, "raw": m.group(0)})
        except json.JSONDecodeError:
            # Try regex extraction for path and content if JSON was cut off or contained unescaped quotes
            p_m = re.search(r'"path"\s*:\s*"([^"]+)"', raw_json)
            c_m = re.search(r'"content"\s*:\s*"([\s\S]*?)(?:"\s*\}|\Z)', raw_json)
            if p_m and c_m:
                content_val = c_m.group(1).replace(r"\"", '"').replace(r"\n", "\n").rstrip('"')
                actions.append(
                    {"name": tool_name, "args": {"path": p_m.group(1), "content": content_val}, "raw": m.group(0)}
                )
            else:
                actions.append({"name": tool_name, "args": {"raw_payload": raw_json}, "raw": m.group(0)})

    if actions:
        return actions

    # 2. Check for ```json\n{"action": "write_file", ...}``` or direct {"path": ..., "content": ...}
    json_block_pattern = r"```(?:json)?\s*\n([\s\S]*?)(?:```|$)"
    for m in re.finditer(json_block_pattern, content):
        raw_json = m.group(1).strip()
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                if "action" in parsed and "args" in parsed:
                    actions.append({"name": parsed["action"], "args": parsed["args"], "raw": m.group(0)})
                elif "path" in parsed and "content" in parsed:
                    actions.append({"name": "write_file", "args": parsed, "raw": m.group(0)})
        except Exception:
            pass

    if actions:
        return actions

    # 3. Fallback heuristic: Extract filename(s) and markdown code block(s)
    default_target_path = extract_target_filename(task_prompt, content)
    ignored_langs = {"bash", "sh", "shell", "cmd", "powershell", "terminal", "zsh"}
    ignored_names = {"node.js", "react.js", "vue.js", "next.js", "express.js", "three.js", "angular.js"}
    seen_paths = set()

    for m in re.finditer(r"```([a-zA-Z0-9_\-.:]*)\s*\n([\s\S]*?)(?:```|$)", content):
        lang_tag = m.group(1).lower().strip()
        code_body = m.group(2).strip()
        if not code_body:
            continue

        if lang_tag.startswith("action:") or lang_tag.startswith("tool:"):
            continue

        if lang_tag in ignored_langs or (
            not lang_tag and any(cmd in code_body for cmd in ("cd ", "npm ", "python -m http"))
        ):
            continue

        if r"\"" in code_body:
            code_body = code_body.replace(r"\"", '"')

        # Look for filename in preceding text
        preceding = content[max(0, m.start() - 250) : m.start()]
        fn_match = re.search(
            r"[`*'\"]*([a-zA-Z0-9_\-./\\]+\.(?:html?|css|js|ts|jsx|tsx|py|json|md|txt|ya?ml|sql))[`*'\"]*",
            preceding,
            re.IGNORECASE,
        )

        target_path = None
        if fn_match:
            candidate = fn_match.group(1).strip("`*'\"").rstrip(".,;:)")
            if candidate and "." in candidate and candidate.lower() not in ignored_names:
                target_path = candidate

        if not target_path:
            if ":" in lang_tag:
                target_path = lang_tag.split(":", 1)[1].strip()
            elif "." in lang_tag and lang_tag not in ignored_names:
                target_path = lang_tag

        if not target_path:
            if "<!doctype html" in code_body.lower() or "<html" in code_body.lower() or lang_tag in ("html", "htm"):
                target_path = (
                    default_target_path
                    if (default_target_path and default_target_path.endswith((".html", ".htm")))
                    else "index.html"
                )
            elif lang_tag == "css":
                target_path = "style.css"
            elif lang_tag in ("js", "javascript"):
                target_path = "script.js"
            elif lang_tag in ("py", "python"):
                target_path = "app.py"
            elif len(actions) == 0 and default_target_path:
                target_path = default_target_path

        if target_path and target_path not in seen_paths:
            seen_paths.add(target_path)
            # If HTML file was truncated before closing tags, close them gracefully
            if target_path.endswith((".html", ".htm")):
                if "<html" in code_body.lower() and "</html>" not in code_body.lower():
                    if "</body>" not in code_body.lower():
                        code_body += "\n</body>"
                    code_body += "\n</html>\n"

            actions.append(
                {
                    "id": None,
                    "name": "write_file",
                    "args": {"path": target_path, "content": code_body},
                    "native": False,
                    "raw": m.group(0),
                }
            )

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
        task_prompt = clean_typos(task_prompt)
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
                try:
                    resp = self.client.chat(
                        messages=messages,
                        tools=TOOL_DEFINITIONS,
                        policy=policy,
                        temperature=temperature,
                        max_output_tokens=3072,
                    )
                except TypeError:
                    resp = self.client.chat(
                        messages=messages,
                        tools=TOOL_DEFINITIONS,
                        policy=policy,
                        temperature=temperature,
                    )

                choices = resp.get("choices", [])
                choice_msg = choices[0].get("message", {}) if choices else {}
                content = choice_msg.get("content") or ""
                native_tool_calls = choice_msg.get("tool_calls") or []

                # Fallback if model choked on native tools
                if not content.strip() and not native_tool_calls:
                    try:
                        resp = self.client.chat(
                            messages=messages,
                            policy=policy,
                            temperature=temperature,
                            max_output_tokens=3072,
                        )
                    except TypeError:
                        resp = self.client.chat(
                            messages=messages,
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
                block_actions = extract_action_blocks(content, task_prompt=task_prompt)
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

            # 2. If no actions were requested, check if we need to nudge or if finished
            if not actions_to_run:
                is_create_intent = bool(
                    re.search(r"\b(create|make|write|touch)\b.*\b(file|script|folder)\b", task_prompt, re.IGNORECASE)
                )
                if step == 1 and is_create_intent:
                    console.print("[dim]Model provided text. Requesting file write action block...[/dim]")
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You described the file in conversational text, but did not output an action code block. "
                                "To create the file on disk, you MUST output:\n"
                                "```action:write_file\n"
                                '{"path": "<filename>", "content": "<exact file content>"}\n'
                                "```\n"
                                "Please output the action block now."
                            ),
                        }
                    )
                    continue

                result.final_response = content
                if content.strip():
                    console.print(f"\n[bold green]Agent Response:[/]\n{content.strip()}\n")
                break

            # If all requested actions are duplicate writes of files already created, finish
            is_redundant = True
            for act in actions_to_run:
                target_path = act["args"].get("path")
                if act["name"] == "write_file" and target_path not in result.files_created:
                    is_redundant = False
                elif act["name"] != "write_file":
                    is_redundant = False

            if is_redundant and result.files_created:
                result.final_response = content
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

                success, tool_res = execute_tool(name, args, cwd=work_dir)

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
                feedback_prompt += (
                    "\n\nIf the task is now complete, provide your final response and summary without outputting further action blocks. "
                    "Otherwise, output the next action block."
                )
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

    def execute_interactive_turn(
        self,
        user_input: str,
        conversation: List[Dict[str, Any]],
        policy: str = "adaptive",
        mode: str = "auto",
        temperature: float = 0.2,
        cwd: Optional[Path | str] = None,
        use_stream: bool = True,
        indent: int = 4,
    ) -> None:
        """Executes one turn of interactive chat with tool calling, multi-step execution, and verification."""
        indent_str = " " * indent
        work_dir = Path(cwd or ".").resolve()

        # 1. Ensure system prompt with workspace context is present
        if not conversation or conversation[0].get("role") != "system":
            system_msg = (
                f"{AGENT_SYSTEM_PROMPT}\n\nWorkspace Directory: {work_dir}\n"
                "All relative file paths resolve against this workspace directory."
            )
            conversation.insert(0, {"role": "system", "content": system_msg})

        # Sanitize conversation to avoid empty text turns
        conversation[:] = [
            m
            for m in conversation
            if (m.get("content") or "").strip() or m.get("tool_calls") or m.get("role") == "tool"
        ]

        conversation.append({"role": "user", "content": user_input})

        step = 0
        while step < self.max_steps:
            step += 1
            full_reply = ""
            meta_chunk: Optional[Dict[str, Any]] = None
            streamed_tool_calls: List[Dict[str, Any]] = []

            try:
                if use_stream:
                    with console.status(f"{indent_str}[dim cyan]Thinking...[/dim cyan]", spinner="dots") as status:
                        try:
                            stream_iter = self.client.stream_chat(
                                conversation,
                                policy=policy,
                                mode=mode,
                                temperature=temperature,
                                tools=TOOL_DEFINITIONS,
                            )
                        except TypeError:
                            try:
                                stream_iter = self.client.stream_chat(
                                    conversation,
                                    policy=policy,
                                    temperature=temperature,
                                    tools=TOOL_DEFINITIONS,
                                )
                            except TypeError:
                                stream_iter = self.client.stream_chat(
                                    conversation,
                                    policy=policy,
                                    temperature=temperature,
                                )
                        first_chunk = None
                        for chunk in stream_iter:
                            first_chunk = chunk
                            break
                        status.stop()

                    def write_stream_content(content: str) -> None:
                        for char in content:
                            if char == "\n":
                                sys.stdout.write(f"\n{indent_str}")
                            else:
                                sys.stdout.write(char)
                        sys.stdout.flush()

                    console.print()
                    sys.stdout.write(indent_str)

                    if first_chunk:
                        choices = first_chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            delta_content = delta.get("content")
                            delta_tc = delta.get("tool_calls")
                            if delta_content:
                                write_stream_content(delta_content)
                                full_reply += delta_content
                            if delta_tc:
                                streamed_tool_calls.extend(delta_tc)
                        if "usage" in first_chunk or "routing" in first_chunk:
                            meta_chunk = first_chunk
                        if "tool_calls" in first_chunk:
                            streamed_tool_calls.extend(first_chunk["tool_calls"])

                    for chunk in stream_iter:
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            delta_content = delta.get("content")
                            delta_tc = delta.get("tool_calls")
                            if delta_content:
                                write_stream_content(delta_content)
                                full_reply += delta_content
                            if delta_tc:
                                streamed_tool_calls.extend(delta_tc)
                        if "usage" in chunk or "routing" in chunk:
                            meta_chunk = chunk
                        if "tool_calls" in chunk:
                            streamed_tool_calls.extend(chunk["tool_calls"])

                    sys.stdout.write("\n\n")
                    sys.stdout.flush()

                else:
                    with console.status(f"{indent_str}[dim cyan]Thinking...[/dim cyan]", spinner="dots"):
                        try:
                            resp = self.client.chat(
                                conversation,
                                policy=policy,
                                mode=mode,
                                temperature=temperature,
                                tools=TOOL_DEFINITIONS,
                            )
                        except TypeError:
                            try:
                                resp = self.client.chat(
                                    conversation,
                                    policy=policy,
                                    temperature=temperature,
                                    tools=TOOL_DEFINITIONS,
                                )
                            except TypeError:
                                resp = self.client.chat(
                                    conversation,
                                    policy=policy,
                                    temperature=temperature,
                                )

                    choices = resp.get("choices", [])
                    choice_msg = choices[0].get("message", {}) if choices else {}
                    full_reply = choice_msg.get("content") or ""
                    streamed_tool_calls = choice_msg.get("tool_calls") or []
                    meta_chunk = resp

                    if full_reply.strip() and not streamed_tool_calls:
                        console.print()
                        indented_lines = "\n".join(f"{indent_str}{line}" for line in full_reply.splitlines())
                        console.print(indented_lines)
                        console.print()

            except Exception as exc:
                if conversation and conversation[-1].get("role") == "user":
                    conversation.pop()
                raise exc

            # Parse tool actions
            actions_to_run: List[Dict[str, Any]] = []
            if streamed_tool_calls:
                for tc in streamed_tool_calls:
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
                block_actions = extract_action_blocks(full_reply, task_prompt=user_input)
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

            # Check if finished or need nudging
            if not actions_to_run:
                is_create_intent = bool(
                    re.search(
                        r"\b(create|make|write|touch)\b.*\b(file|script|folder)\b",
                        user_input,
                        re.IGNORECASE,
                    )
                )
                if step == 1 and is_create_intent:
                    console.print(
                        f"{indent_str}[dim]Model provided text description. Requesting file write action...[/dim]"
                    )
                    conversation.append({"role": "assistant", "content": full_reply})
                    conversation.append(
                        {
                            "role": "user",
                            "content": (
                                "You described the file in conversational text, but did not execute a tool call or output an action code block. "
                                "To create the file on disk, you MUST call the write_file tool or output:\n"
                                "```action:write_file\n"
                                '{"path": "<filename>", "content": "<exact file content>"}\n'
                                "```\n"
                                "Please create the file on disk now."
                            ),
                        }
                    )
                    continue

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
                        policy=routing.get("policy", policy),
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
                        indent=indent,
                    )
                break

            # Execute actions with verification
            tool_outputs: List[Dict[str, Any]] = []
            for act in actions_to_run:
                name = act["name"]
                args = act["args"]

                args_preview = ", ".join(
                    f"{k}='{v}'" if not isinstance(v, str) or len(v) < 35 else f"{k}='{v[:32]}...'"
                    for k, v in args.items()
                )
                console.print(f"{indent_str}[bold yellow]⚙ Action:[/] [cyan]{name}[/]({args_preview})")

                success, tool_res = execute_tool(name, args, cwd=work_dir)

                if success:
                    console.print(f"{indent_str}[bold green]✔[/] {tool_res}")
                else:
                    console.print(f"{indent_str}[bold red]✖[/] {tool_res}")

                tool_outputs.append(
                    {
                        "call_id": act.get("id"),
                        "name": name,
                        "success": success,
                        "output": tool_res,
                        "native": act.get("native", False),
                    }
                )

            # Feed tool outputs back into conversation history
            if streamed_tool_calls:
                conversation.append(
                    {
                        "role": "assistant",
                        "content": full_reply,
                        "tool_calls": streamed_tool_calls,
                    }
                )
                for out in tool_outputs:
                    conversation.append(
                        {
                            "role": "tool",
                            "tool_call_id": out["call_id"] or "call_unknown",
                            "name": out["name"],
                            "content": out["output"],
                        }
                    )
            else:
                conversation.append({"role": "assistant", "content": full_reply})
                feedback_lines = [f"Result of {out['name']}:\n{out['output']}" for out in tool_outputs]
                feedback_prompt = "\n\n".join(feedback_lines)
                feedback_prompt += (
                    "\n\nIf the task is now complete, provide your final response and summary without outputting further action blocks. "
                    "Otherwise, output the next action block."
                )
                conversation.append({"role": "user", "content": feedback_prompt})
