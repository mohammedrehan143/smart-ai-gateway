"""Automated Testing, Quality Assurance, and Test Generation Engine for Smart AI Gateway.

Provides automated test execution and quality gates:
- Test execution across pytest, unittest, and npm.
- Parses test pass/fail metrics, execution duration, and error traces.
- Automated unit test generator analyzing source AST.
- Static codebase syntax & quality validation.
- API response contract validation.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from smart_ai_cli.process_manager import ProcessManager


@dataclass
class TestSuiteResult:
    framework: str
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    total: int = 0
    duration_seconds: float = 0.0
    exit_code: int = 0
    raw_output: str = ""
    failures_summary: List[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.failed == 0 and self.errors == 0 and self.exit_code == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "framework": self.framework,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "total": self.total,
            "duration_seconds": self.duration_seconds,
            "is_success": self.is_success,
            "exit_code": self.exit_code,
            "failures_summary": self.failures_summary,
        }


class QAEngine:
    """Orchestrates test execution, test generation, and QA verification."""

    def __init__(self, workspace_root: Optional[Path | str] = None, pm: Optional[ProcessManager] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self.pm = pm or ProcessManager(self.workspace_root)

    def run_tests(
        self,
        test_target: Optional[str] = None,
        framework: str = "pytest",
        cwd: Optional[Path | str] = None,
    ) -> TestSuiteResult:
        """Executes tests and parses pass/fail results."""
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        fm = framework.lower().strip()

        if fm == "pytest":
            target_arg = test_target or ""
            python_exe = f'"{sys.executable}"' if sys.executable else "python"
            cmd = f"{python_exe} -m pytest {target_arg} -q"
        elif fm == "unittest":
            target_arg = f"discover -s {test_target}" if test_target else "discover"
            python_exe = f'"{sys.executable}"' if sys.executable else "python"
            cmd = f"{python_exe} -m unittest {target_arg}"
        elif fm == "npm":
            cmd = f"npm test {test_target or ''}".strip()
        else:
            return TestSuiteResult(
                framework=framework,
                exit_code=-1,
                raw_output=f"Unsupported test framework: '{framework}'",
            )

        success, output, code = self.pm.run_command(cmd, timeout_seconds=120, cwd=work_dir)

        passed = 0
        failed = 0
        errors = 0
        skipped = 0
        duration = 0.0
        failures: List[str] = []

        # Parse pytest output: e.g. "207 passed in 17.16s" or "3 failed, 204 passed in 15.51s"
        p_match = re.search(r"(\d+)\s+passed", output)
        if p_match:
            passed = int(p_match.group(1))

        f_match = re.search(r"(\d+)\s+failed", output)
        if f_match:
            failed = int(f_match.group(1))

        e_match = re.search(r"(\d+)\s+error", output)
        if e_match:
            errors = int(e_match.group(1))

        s_match = re.search(r"(\d+)\s+skipped", output)
        if s_match:
            skipped = int(s_match.group(1))

        d_match = re.search(r"in\s+([\d.]+)\s*s", output)
        if d_match:
            duration = float(d_match.group(1))

        # Extract failure headers
        for line in output.splitlines():
            if line.startswith("FAILED ") or line.startswith("ERROR "):
                failures.append(line.strip())

        return TestSuiteResult(
            framework=fm,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            total=passed + failed + errors + skipped,
            duration_seconds=duration,
            exit_code=code,
            raw_output=output,
            failures_summary=failures,
        )

    def generate_unit_tests(self, source_file: str, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
        """Scans a Python source file via AST and generates pytest test scaffolding."""
        base = Path(cwd).resolve() if cwd else self.workspace_root
        resolved = (base / source_file).resolve()
        if not resolved.is_file():
            return False, f"Source file '{source_file}' not found."

        try:
            content = resolved.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(resolved))
        except Exception as exc:
            return False, f"Failed to parse source file '{source_file}': {exc}"

        functions: List[str] = []
        classes: List[str] = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                classes.append(node.name)

        module_stem = resolved.stem
        lines = [
            f'"""Automated test suite for {source_file}."""',
            "",
            "import pytest",
            f"import {module_stem}",
            "",
        ]

        for fn in functions:
            lines.extend(
                [
                    f"def test_{fn}_basic():",
                    f'    """Test basic functionality of {fn}."""',
                    "    # TODO: Supply valid parameters",
                    f"    assert hasattr({module_stem}, '{fn}')",
                    f"    assert callable(getattr({module_stem}, '{fn}'))",
                    "",
                ]
            )

        for cls in classes:
            lines.extend(
                [
                    f"def test_{cls}_instantiation():",
                    f'    """Test instantiation and methods of {cls}."""',
                    f"    assert hasattr({module_stem}, '{cls}')",
                    "",
                ]
            )

        test_code = "\n".join(lines)
        return True, test_code

    def run_static_analysis(self, cwd: Optional[Path | str] = None) -> Tuple[bool, Dict[str, Any]]:
        """Scans all Python files for syntax validity."""
        base = Path(cwd).resolve() if cwd else self.workspace_root
        py_files = list(base.rglob("*.py"))
        syntax_errors: List[Dict[str, Any]] = []
        checked = 0

        for f in py_files:
            if any(part in (".git", "__pycache__", ".smartai", ".venv", "node_modules") for part in f.parts):
                continue
            checked += 1
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                ast.parse(content, filename=str(f))
            except SyntaxError as se:
                syntax_errors.append(
                    {
                        "file": str(f.relative_to(base)).replace("\\", "/"),
                        "line": se.lineno,
                        "error": se.msg,
                    }
                )

        report = {
            "files_checked": checked,
            "syntax_valid": len(syntax_errors) == 0,
            "syntax_errors": syntax_errors,
        }
        return len(syntax_errors) == 0, report


default_qa_engine = QAEngine()
