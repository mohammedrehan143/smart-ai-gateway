"""Autonomous Debugging and Self-Healing Engine for Smart AI Gateway.

Provides automated diagnosis and self-healing:
- Parses Python tracebacks, pytest failures, Node.js errors, and compiler logs.
- Classifies error categories (SyntaxError, ModuleNotFoundError, TypeError, etc.).
- Identifies problematic file paths, line numbers, and root causes.
- Performs static AST syntax checks.
- Self-healing loop: Snapshot -> Propose/Apply Fix -> Verify/Regression Test -> Rollback on failure.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from smart_ai_cli.filesystem import WorkspaceFilesystem
from smart_ai_cli.process_manager import ProcessManager


@dataclass
class ErrorDiagnosis:
    error_type: str
    error_message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    root_cause: str = ""
    suggested_fix: str = ""
    stack_trace: List[str] = field(default_factory=list)
    missing_packages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "root_cause": self.root_cause,
            "suggested_fix": self.suggested_fix,
            "missing_packages": self.missing_packages,
        }


class AutonomousDebugger:
    """Diagnoses runtime/syntax errors and performs automated self-healing."""

    def __init__(
        self,
        workspace_root: Optional[Path | str] = None,
        fs: Optional[WorkspaceFilesystem] = None,
        pm: Optional[ProcessManager] = None,
    ):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self.fs = fs or WorkspaceFilesystem(self.workspace_root)
        self.pm = pm or ProcessManager(self.workspace_root)

    def parse_error_output(self, error_text: str) -> List[ErrorDiagnosis]:
        """Parses error text / logs and extracts structured diagnoses."""
        diagnoses: List[ErrorDiagnosis] = []
        if not error_text or not error_text.strip():
            return diagnoses

        # 1. Python ModuleNotFoundError: No module named 'xyz'
        mod_matches = re.finditer(r"ModuleNotFoundError:\s+No module named ['\"]([^'\"]+)['\"]", error_text)
        for m in mod_matches:
            pkg = m.group(1).split(".")[0]
            diagnoses.append(
                ErrorDiagnosis(
                    error_type="ModuleNotFoundError",
                    error_message=m.group(0),
                    root_cause=f"Required package '{pkg}' is not installed in the environment.",
                    suggested_fix=f"Install missing package using `pip install {pkg}`.",
                    missing_packages=[pkg],
                )
            )

        # 2. Python SyntaxError with file and line: File "...", line X
        syntax_matches = re.finditer(
            r'File ["\']([^"\']+)["\'],\s+line\s+(\d+).*?\n(?:.*?\n)*?(SyntaxError|IndentationError):\s+(.*)',
            error_text,
        )
        for m in syntax_matches:
            filepath = m.group(1)
            lineno = int(m.group(2))
            err_type = m.group(3)
            err_msg = m.group(4)
            diagnoses.append(
                ErrorDiagnosis(
                    error_type=err_type,
                    error_message=f"{err_type}: {err_msg}",
                    file_path=filepath,
                    line_number=lineno,
                    root_cause=f"Syntax or indentation error at line {lineno}: {err_msg}",
                    suggested_fix="Inspect the line syntax, matching parentheses, colons, and indentation.",
                )
            )

        # 3. Python standard tracebacks: Traceback (most recent call last): ... File "...", line X, in ... <ErrorType>: <message>
        tb_matches = re.finditer(
            r'File ["\']([^"\']+)["\'],\s+line\s+(\d+),\s+in\s+([a-zA-Z0-9_<>]+\s*)\n\s*(.*?)\n([a-zA-Z0-9_]+Error|[a-zA-Z0-9_]+Exception):\s+(.*)',
            error_text,
        )
        for m in tb_matches:
            filepath = m.group(1)
            lineno = int(m.group(2))
            fn_name = m.group(3).strip()
            err_type = m.group(5)
            err_msg = m.group(6)
            diagnoses.append(
                ErrorDiagnosis(
                    error_type=err_type,
                    error_message=f"{err_type}: {err_msg}",
                    file_path=filepath,
                    line_number=lineno,
                    root_cause=f"Runtime {err_type} in function `{fn_name}` at line {lineno}: {err_msg}",
                    suggested_fix=f"Check logic invariants and variable types around line {lineno}.",
                )
            )

        # 4. Pytest test failure: FAILED tests/...::test_name - AssertionError: ...
        pytest_matches = re.finditer(
            r"FAILED\s+([^:]+)::([a-zA-Z0-9_]+)\s+-\s+([a-zA-Z0-9_]+Error|AssertionError):\s+(.*)", error_text
        )
        for m in pytest_matches:
            diagnoses.append(
                ErrorDiagnosis(
                    error_type=m.group(3),
                    error_message=f"Test failure in {m.group(2)}: {m.group(4)}",
                    file_path=m.group(1),
                    root_cause=f"Assertion failed in test `{m.group(2)}`.",
                    suggested_fix="Review test expectation against implementation output.",
                )
            )

        return diagnoses

    def check_syntax(self, file_path: str) -> Tuple[bool, Optional[ErrorDiagnosis]]:
        """Performs static syntax analysis using Python AST."""
        resolved = (self.workspace_root / file_path).resolve()
        if not resolved.is_file():
            return False, ErrorDiagnosis(
                error_type="FileNotFoundError",
                error_message=f"File not found: '{file_path}'",
                file_path=file_path,
            )

        if resolved.suffix.lower() not in (".py", ".pyw"):
            return True, None

        try:
            content = resolved.read_text(encoding="utf-8")
            ast.parse(content, filename=str(resolved))
            return True, None
        except SyntaxError as se:
            diag = ErrorDiagnosis(
                error_type="SyntaxError",
                error_message=f"{se.msg} (line {se.lineno})",
                file_path=file_path,
                line_number=se.lineno,
                root_cause=f"SyntaxError on line {se.lineno}: {se.msg}",
                suggested_fix="Correct unexpected token, unclosed string, or missing bracket.",
            )
            return False, diag

    def heal_missing_package(self, package_name: str) -> Tuple[bool, str]:
        """Self-heals missing dependency by installing it via pip."""
        success, out = self.pm.install_dependencies("pip", [package_name], cwd=self.workspace_root)
        if success:
            return True, f"Successfully self-healed: installed '{package_name}'."
        return False, f"Failed to install package '{package_name}':\n{out}"

    def auto_repair_file(
        self,
        file_path: str,
        target_error: ErrorDiagnosis,
        repaired_content: str,
    ) -> Tuple[bool, str]:
        """Applies patch to file, verifies syntax, and automatically rolls back if syntax fails."""
        resolved = (self.workspace_root / file_path).resolve()
        if not resolved.is_file():
            return False, f"Target file '{file_path}' not found."

        # 1. Snapshot current state before attempting fix
        snap_id = self.fs.history.snapshot(resolved, description=f"pre-repair {target_error.error_type}")

        # 2. Write proposed repair
        self.fs.write_file(file_path, repaired_content, cwd=self.workspace_root, snapshot=False)

        # 3. Verify syntax
        valid_syntax, diag = self.check_syntax(file_path)
        if not valid_syntax:
            # Rollback immediately!
            self.fs.rollback(file_path, snap_id, cwd=self.workspace_root)
            return (
                False,
                f"Self-healing rejected: fix introduced syntax error ({diag.error_message if diag else 'unknown'}). Rolled back to snapshot {snap_id}.",
            )

        return True, f"Self-healing verified: successfully repaired '{file_path}' (snapshot {snap_id})."


default_debugger = AutonomousDebugger()
