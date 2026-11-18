"""Local filesystem and execution tools for the Smart AI CLI Autonomous Agent."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or overwrite an existing file with the specified content. Automatically creates parent directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute file path to create or overwrite.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The exact full text content to write into the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edits an existing file by replacing an exact target string with replacement text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to edit.",
                    },
                    "target": {
                        "type": "string",
                        "description": "The exact text block currently inside the file to be replaced.",
                    },
                    "replacement": {
                        "type": "string",
                        "description": "The new text that will replace the target text.",
                    },
                },
                "required": ["path", "target", "replacement"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads the text contents of a file, optionally within a line range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path of the file to read.",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Optional starting line number (1-based, inclusive).",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Optional ending line number (1-based, inclusive).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lists the files and folders inside a given directory path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to inspect (defaults to current directory '.').",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Whether to list recursively (default false).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Executes a shell command in the current working directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command line string to run.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Maximum seconds to allow before aborting (default 30).",
                    },
                },
                "required": ["command"],
            },
        },
    },
]

AGENT_SYSTEM_PROMPT = """You are an autonomous AI software engineer and terminal agent connected to the user's workspace via Smart AI Gateway.
You have direct access to tools to inspect and modify the local filesystem.

MANDATORY EXECUTION FORMAT:
To create, edit, read, or list files or run shell commands, you MUST output your action using an action code block.
DO NOT just talk about creating the file or show normal text. If you do not output an action code block, the file WILL NOT be created on disk!

To create or overwrite a file:
```action:write_file
{
  "path": "filename.ext",
  "content": "exact full content of the file"
}
```

To edit an existing file:
```action:edit_file
{
  "path": "filename.ext",
  "target": "exact text block to replace",
  "replacement": "new replacement text"
}
```

To read a file:
```action:read_file
{
  "path": "filename.ext"
}
```

To list a directory:
```action:list_directory
{
  "path": "."
}
```

To run a shell command:
```action:run_command
{
  "command": "shell command here"
}
```

RULES:
1. When asked to create, edit, write, or examine files, YOU MUST EXECUTE the appropriate tool using the action format above.
2. Provide valid JSON inside the action code block.
3. You can execute multiple action blocks sequentially if needed.
4. After executing actions, verify results and provide a concise summary.
"""


def write_file(path: str, content: str) -> Tuple[bool, str]:
    """Creates or overwrites a file with content."""
    try:
        resolved = Path(path).resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        size = resolved.stat().st_size
        return True, f"Successfully created {path} ({size} bytes)"
    except Exception as exc:
        return False, f"Failed to write file '{path}': {exc}"


def edit_file(path: str, target: str, replacement: str) -> Tuple[bool, str]:
    """Replaces target string in an existing file with replacement string."""
    try:
        resolved = Path(path).resolve()
        if not resolved.is_file():
            return False, f"File not found: '{path}'"

        text = resolved.read_text(encoding="utf-8")
        if target not in text:
            return False, f"Target text not found in '{path}'. Make sure exact characters and indentation match."

        updated = text.replace(target, replacement, 1)
        resolved.write_text(updated, encoding="utf-8")
        return True, f"Successfully updated '{path}'."
    except Exception as exc:
        return False, f"Failed to edit file '{path}': {exc}"


def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Tuple[bool, str]:
    """Reads file contents, optionally slicing by line numbers (1-indexed)."""
    try:
        resolved = Path(path).resolve()
        if not resolved.is_file():
            return False, f"File not found: '{path}'"

        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        total = len(lines)

        s = max(1, start_line) if start_line is not None else 1
        e = min(total, end_line) if end_line is not None else total

        selected = lines[s - 1 : e]
        numbered = [f"{i + s:4d} | {line}" for i, line in enumerate(selected)]
        output = "".join(numbered)
        return True, output if output else "(file is empty)"
    except Exception as exc:
        return False, f"Failed to read file '{path}': {exc}"


def list_directory(path: Optional[str] = None, recursive: bool = False) -> Tuple[bool, str]:
    """Lists files and directories in path."""
    try:
        target = Path(path or ".").resolve()
        if not target.exists():
            return False, f"Directory not found: '{path}'"

        items = []
        if recursive:
            for p in sorted(target.rglob("*")):
                # Skip .git and __pycache__
                if ".git" in p.parts or "__pycache__" in p.parts:
                    continue
                rel = p.relative_to(target)
                if p.is_dir():
                    items.append(f"[DIR]  {rel}/")
                else:
                    items.append(f"[FILE] {rel} ({p.stat().st_size} bytes)")
        else:
            for p in sorted(target.iterdir()):
                if p.name in (".git", "__pycache__"):
                    continue
                if p.is_dir():
                    items.append(f"[DIR]  {p.name}/")
                else:
                    items.append(f"[FILE] {p.name} ({p.stat().st_size} bytes)")

        return True, "\n".join(items) if items else "(directory is empty)"
    except Exception as exc:
        return False, f"Failed to list directory '{path}': {exc}"


def run_command(command: str, timeout_seconds: int = 30) -> Tuple[bool, str]:
    """Executes a shell command."""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        combined = []
        if out:
            combined.append(f"STDOUT:\n{out}")
        if err:
            combined.append(f"STDERR:\n{err}")
        combined.append(f"Exit Code: {proc.returncode}")
        return proc.returncode == 0, "\n\n".join(combined)
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout_seconds} seconds."
    except Exception as exc:
        return False, f"Command execution error: {exc}"


def execute_tool(name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
    """Dispatches a tool call to the corresponding local execution function."""
    clean_name = name.lower().strip()
    if clean_name == "write_file":
        return write_file(path=args.get("path", ""), content=args.get("content", ""))
    elif clean_name == "edit_file":
        return edit_file(
            path=args.get("path", ""),
            target=args.get("target", ""),
            replacement=args.get("replacement", ""),
        )
    elif clean_name == "read_file":
        return read_file(
            path=args.get("path", ""),
            start_line=args.get("start_line"),
            end_line=args.get("end_line"),
        )
    elif clean_name == "list_directory":
        return list_directory(
            path=args.get("path"),
            recursive=bool(args.get("recursive", False)),
        )
    elif clean_name == "run_command":
        return run_command(
            command=args.get("command", ""),
            timeout_seconds=int(args.get("timeout_seconds", 30)),
        )
    else:
        return False, f"Unknown tool: '{name}'"
