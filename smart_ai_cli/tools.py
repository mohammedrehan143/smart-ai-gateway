"""Local filesystem and execution tools for the Smart AI CLI Autonomous Agent.

Combines WorkspaceFilesystem, FileHistoryManager, and ProcessManager into a unified
execution interface for both CLI Autonomous Agent and backend Strong Agent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from smart_ai_cli.filesystem import WorkspaceFilesystem, default_workspace_fs
from smart_ai_cli.process_manager import ProcessManager, default_process_manager

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or overwrite an existing file with the specified content. Automatically creates parent directories and creates a version snapshot.",
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
            "description": "Edits an existing file by replacing an exact target string with replacement text, snapshotting before change.",
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
            "name": "delete_file",
            "description": "Deletes a file after recording a recovery snapshot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path of the file to delete.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_file",
            "description": "Renames a file or directory from old_path to new_path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "old_path": {"type": "string", "description": "Existing path."},
                    "new_path": {"type": "string", "description": "New target path."},
                },
                "required": ["old_path", "new_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Moves a file or directory to a new destination.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source path."},
                    "destination": {"type": "string", "description": "Destination path."},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Copies a file to a new destination and verifies copy integrity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source file path."},
                    "destination": {"type": "string", "description": "Destination file path."},
                    "overwrite": {
                        "type": "boolean",
                        "description": "Whether to overwrite existing destination (default true).",
                    },
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "Creates a directory recursively.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to create."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_directory",
            "description": "Deletes a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to delete."},
                    "recursive": {"type": "boolean", "description": "Whether to delete recursively (default true)."},
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
            "name": "find_files",
            "description": "Finds files matching a glob pattern (e.g. '*.py', '**/*.tsx').",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern to match."},
                    "path": {"type": "string", "description": "Base directory to search in (default '.')."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_files",
            "description": "Grep search inside file contents matching text or regex pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search string or regex."},
                    "path": {"type": "string", "description": "Base directory (default '.')."},
                    "file_pattern": {"type": "string", "description": "Filename pattern filter (default '*')."},
                    "is_regex": {"type": "boolean", "description": "Whether query is a regex."},
                    "case_sensitive": {"type": "boolean", "description": "Whether search is case-sensitive."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rollback_file",
            "description": "Rolls back a file to its previous or specific snapshot version.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path of the file to rollback."},
                    "snapshot_id": {"type": "string", "description": "Optional specific snapshot ID to restore."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_diff",
            "description": "Shows unified diff between current file and snapshot version.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path."},
                    "snapshot_id": {"type": "string", "description": "Optional snapshot ID."},
                },
                "required": ["path"],
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
                        "description": "Maximum seconds to allow before aborting (default 60).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_script",
            "description": "Executes a script file using the appropriate runtime interpreter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "script_path": {"type": "string", "description": "Path to the script file."},
                    "interpreter": {
                        "type": "string",
                        "description": "Optional interpreter command (e.g. 'python', 'node').",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Arguments to pass to script.",
                    },
                    "timeout_seconds": {"type": "integer", "description": "Timeout in seconds."},
                },
                "required": ["script_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_background_process",
            "description": "Starts a background process (e.g., development server) and returns process ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run in background."},
                    "process_name": {"type": "string", "description": "Optional descriptive name."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_background_process",
            "description": "Stops a running background process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process ID or name."},
                },
                "required": ["process_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_process_status",
            "description": "Gets current status and recent log output of a background process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process ID or name."},
                    "tail_lines": {"type": "integer", "description": "Number of log lines to return (default 30)."},
                },
                "required": ["process_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_background_processes",
            "description": "Lists all background processes and their running status.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_dependencies",
            "description": "Installs dependencies using pip, npm, yarn, pnpm, or cargo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_manager": {"type": "string", "description": "pip, npm, yarn, pnpm, or cargo."},
                    "packages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of packages.",
                    },
                },
                "required": ["package_manager"],
            },
        },
    },
]

AGENT_SYSTEM_PROMPT = """You are an autonomous AI software engineer and terminal agent connected to the user's workspace via Smart AI Gateway.
You have direct access to tools to inspect and modify the local filesystem, run terminal commands, manage background processes, and verify code.

Provide clear, direct, and well-structured answers without outputting internal policy thoughts, chain-of-thought traces, or scratchpad notes.

When asked to create, edit, read, or list files or run shell commands:
1. Clearly specify the target file path (e.g. `File: filename.ext` or `filename.ext`).
2. Provide the complete, production-ready code inside a markdown code block.
3. You can also output action code blocks:

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

To delete a file:
```action:delete_file
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

To find files matching a pattern:
```action:find_files
{
  "pattern": "*.py"
}
```

To search code inside files:
```action:search_in_files
{
  "query": "def my_func"
}
```

To run a shell command:
```action:run_command
{
  "command": "shell command here"
}
```

To rollback a file:
```action:rollback_file
{
  "path": "filename.ext"
}
```

RULES:
1. When asked to create, edit, write, or examine files, always provide full, complete code without placeholders.
2. Always clearly identify the destination filename and path.
"""


def write_file(path: str, content: str, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Creates or overwrites a file with content, verifying the write on disk."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.write_file(path=path, content=content, cwd=cwd)


def edit_file(path: str, target: str, replacement: str, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Replaces target string in an existing file with replacement string and verifies the edit."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.edit_file(path=path, target=target, replacement=replacement, cwd=cwd)


def read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    cwd: Optional[Path | str] = None,
) -> Tuple[bool, str]:
    """Reads file contents, optionally slicing by line numbers (1-indexed)."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.read_file(path=path, start_line=start_line, end_line=end_line, cwd=cwd)


def delete_file(path: str, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Deletes a file, recording a history snapshot."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.delete_file(path=path, cwd=cwd)


def rename_file(old_path: str, new_path: str, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Renames a file or directory."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.rename_file(old_path=old_path, new_path=new_path, cwd=cwd)


def move_file(source: str, destination: str, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Moves a file or directory."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.move_file(source=source, destination=destination, cwd=cwd)


def copy_file(
    source: str, destination: str, overwrite: bool = True, cwd: Optional[Path | str] = None
) -> Tuple[bool, str]:
    """Copies a file to a new destination."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.copy_file(source=source, destination=destination, overwrite=overwrite, cwd=cwd)


def create_directory(path: str, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Creates a directory recursively."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.create_directory(path=path, cwd=cwd)


def delete_directory(path: str, recursive: bool = True, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Deletes a directory."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.delete_directory(path=path, recursive=recursive, cwd=cwd)


def list_directory(
    path: Optional[str] = None,
    recursive: bool = False,
    cwd: Optional[Path | str] = None,
) -> Tuple[bool, str]:
    """Lists files and directories in path."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.list_directory(path=path, recursive=recursive, cwd=cwd)


def find_files(
    pattern: str = "*",
    path: Optional[str] = None,
    cwd: Optional[Path | str] = None,
) -> Tuple[bool, str]:
    """Finds files matching glob pattern."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.find_files(pattern=pattern, path=path, cwd=cwd)


def search_in_files(
    query: str,
    path: Optional[str] = None,
    file_pattern: str = "*",
    is_regex: bool = False,
    case_sensitive: bool = False,
    cwd: Optional[Path | str] = None,
) -> Tuple[bool, str]:
    """Searches for text in files."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.search_in_files(
        query=query,
        path=path,
        file_pattern=file_pattern,
        is_regex=is_regex,
        case_sensitive=case_sensitive,
        cwd=cwd,
    )


def rollback_file(path: str, snapshot_id: Optional[str] = None, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Restores a file to a previous snapshot."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.rollback(path=path, snapshot_id=snapshot_id, cwd=cwd)


def get_file_diff(path: str, snapshot_id: Optional[str] = None, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Generates unified diff between file and snapshot."""
    fs = WorkspaceFilesystem(cwd) if cwd else default_workspace_fs
    return fs.get_diff(path=path, snapshot_id=snapshot_id, cwd=cwd)


def run_command(command: str, timeout_seconds: int = 60, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Executes a shell command in the specified working directory."""
    pm = ProcessManager(cwd) if cwd else default_process_manager
    success, output, _ = pm.run_command(command=command, timeout_seconds=timeout_seconds, cwd=cwd)
    return success, output


def run_script(
    script_path: str,
    interpreter: Optional[str] = None,
    args: Optional[List[str]] = None,
    timeout_seconds: int = 60,
    cwd: Optional[Path | str] = None,
) -> Tuple[bool, str]:
    """Executes a script with a given or inferred interpreter."""
    pm = ProcessManager(cwd) if cwd else default_process_manager
    success, output, _ = pm.run_script(
        script_path=script_path,
        interpreter=interpreter,
        args=args,
        timeout_seconds=timeout_seconds,
        cwd=cwd,
    )
    return success, output


def start_background_process(
    command: str,
    process_name: Optional[str] = None,
    cwd: Optional[Path | str] = None,
) -> Tuple[bool, str]:
    """Starts a process in the background."""
    pm = ProcessManager(cwd) if cwd else default_process_manager
    success, msg, _ = pm.start_background_process(command=command, process_name=process_name, cwd=cwd)
    return success, msg


def stop_background_process(process_id: str, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Stops a background process."""
    pm = ProcessManager(cwd) if cwd else default_process_manager
    return pm.stop_background_process(process_id)


def get_process_status(process_id: str, tail_lines: int = 30, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Gets status and logs of a background process."""
    pm = ProcessManager(cwd) if cwd else default_process_manager
    ok, status = pm.get_process_status(process_id, tail_lines)
    if ok:
        return True, json.dumps(status, indent=2)
    return False, status.get("error", "Unknown error")


def list_background_processes(cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Lists all background processes."""
    pm = ProcessManager(cwd) if cwd else default_process_manager
    procs = pm.list_background_processes()
    return True, json.dumps(procs, indent=2) if procs else "No background processes currently active."


def install_dependencies(
    package_manager: str,
    packages: Optional[List[str]] = None,
    cwd: Optional[Path | str] = None,
) -> Tuple[bool, str]:
    """Installs dependencies via package manager."""
    pm = ProcessManager(cwd) if cwd else default_process_manager
    return pm.install_dependencies(package_manager=package_manager, packages=packages, cwd=cwd)


def execute_tool(name: str, args: Dict[str, Any], cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Dispatches a tool call to the corresponding local execution function."""
    clean_name = name.lower().strip()

    # Core Filesystem Tools
    if clean_name == "write_file":
        return write_file(path=args.get("path", ""), content=args.get("content", ""), cwd=cwd)
    elif clean_name == "edit_file":
        return edit_file(
            path=args.get("path", ""),
            target=args.get("target", ""),
            replacement=args.get("replacement", ""),
            cwd=cwd,
        )
    elif clean_name == "read_file":
        return read_file(
            path=args.get("path", ""),
            start_line=args.get("start_line"),
            end_line=args.get("end_line"),
            cwd=cwd,
        )
    elif clean_name == "delete_file":
        return delete_file(path=args.get("path", ""), cwd=cwd)
    elif clean_name == "rename_file":
        return rename_file(old_path=args.get("old_path", ""), new_path=args.get("new_path", ""), cwd=cwd)
    elif clean_name == "move_file":
        return move_file(source=args.get("source", ""), destination=args.get("destination", ""), cwd=cwd)
    elif clean_name == "copy_file":
        return copy_file(
            source=args.get("source", ""),
            destination=args.get("destination", ""),
            overwrite=bool(args.get("overwrite", True)),
            cwd=cwd,
        )
    elif clean_name == "create_directory":
        return create_directory(path=args.get("path", ""), cwd=cwd)
    elif clean_name == "delete_directory":
        return delete_directory(
            path=args.get("path", ""),
            recursive=bool(args.get("recursive", True)),
            cwd=cwd,
        )
    elif clean_name == "list_directory":
        return list_directory(
            path=args.get("path"),
            recursive=bool(args.get("recursive", False)),
            cwd=cwd,
        )
    elif clean_name == "find_files":
        return find_files(
            pattern=args.get("pattern", "*"),
            path=args.get("path"),
            cwd=cwd,
        )
    elif clean_name == "search_in_files":
        return search_in_files(
            query=args.get("query", ""),
            path=args.get("path"),
            file_pattern=args.get("file_pattern", "*"),
            is_regex=bool(args.get("is_regex", False)),
            case_sensitive=bool(args.get("case_sensitive", False)),
            cwd=cwd,
        )
    elif clean_name == "rollback_file":
        return rollback_file(path=args.get("path", ""), snapshot_id=args.get("snapshot_id"), cwd=cwd)
    elif clean_name == "get_file_diff":
        return get_file_diff(path=args.get("path", ""), snapshot_id=args.get("snapshot_id"), cwd=cwd)

    # Process and Execution Tools
    elif clean_name == "run_command":
        return run_command(
            command=args.get("command", ""),
            timeout_seconds=int(args.get("timeout_seconds", 60)),
            cwd=cwd,
        )
    elif clean_name == "run_script":
        return run_script(
            script_path=args.get("script_path", ""),
            interpreter=args.get("interpreter"),
            args=args.get("args"),
            timeout_seconds=int(args.get("timeout_seconds", 60)),
            cwd=cwd,
        )
    elif clean_name == "start_background_process":
        return start_background_process(
            command=args.get("command", ""),
            process_name=args.get("process_name"),
            cwd=cwd,
        )
    elif clean_name == "stop_background_process":
        return stop_background_process(process_id=args.get("process_id", ""), cwd=cwd)
    elif clean_name == "get_process_status":
        return get_process_status(
            process_id=args.get("process_id", ""),
            tail_lines=int(args.get("tail_lines", 30)),
            cwd=cwd,
        )
    elif clean_name == "list_background_processes":
        return list_background_processes(cwd=cwd)
    elif clean_name == "install_dependencies":
        return install_dependencies(
            package_manager=args.get("package_manager", "pip"),
            packages=args.get("packages"),
            cwd=cwd,
        )
    else:
        return False, f"Unknown tool: '{name}'"
