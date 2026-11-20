"""Unit tests for Smart AI Debugger and QA Engine."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from smart_ai_cli.debugger import AutonomousDebugger
from smart_ai_cli.qa_engine import QAEngine


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_debugger_parse_error_output():
    debugger = AutonomousDebugger()

    # 1. ModuleNotFoundError
    log1 = "ModuleNotFoundError: No module named 'fastapi'"
    diags1 = debugger.parse_error_output(log1)
    assert len(diags1) == 1
    assert diags1[0].error_type == "ModuleNotFoundError"
    assert "fastapi" in diags1[0].missing_packages

    # 2. SyntaxError
    log2 = 'File "app/main.py", line 42\n    def broken_func(\n                   ^\nSyntaxError: unexpected EOF while parsing'
    diags2 = debugger.parse_error_output(log2)
    assert len(diags2) == 1
    assert diags2[0].error_type == "SyntaxError"
    assert diags2[0].line_number == 42
    assert "app/main.py" in diags2[0].file_path

    # 3. Traceback
    log3 = 'Traceback (most recent call last):\n  File "calc.py", line 12, in divide\n    return a / b\nZeroDivisionError: division by zero'
    diags3 = debugger.parse_error_output(log3)
    assert len(diags3) == 1
    assert diags3[0].error_type == "ZeroDivisionError"
    assert diags3[0].line_number == 12


def test_debugger_syntax_check_and_auto_repair(temp_workspace):
    debugger = AutonomousDebugger(temp_workspace)

    # Valid syntax
    good_file = temp_workspace / "good.py"
    good_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    ok, diag = debugger.check_syntax("good.py")
    assert ok is True
    assert diag is None

    # Invalid syntax
    bad_file = temp_workspace / "bad.py"
    bad_file.write_text("def add(a, b\n    return a + b\n", encoding="utf-8")
    ok, diag = debugger.check_syntax("bad.py")
    assert ok is False
    assert diag is not None
    assert diag.error_type == "SyntaxError"

    # Attempt broken repair -> should reject and rollback
    repaired_broken = "def add(a, b)::\n    return a + b\n"
    ok, msg = debugger.auto_repair_file("bad.py", diag, repaired_broken)
    assert ok is False
    assert "rejected" in msg
    assert bad_file.read_text(encoding="utf-8") == "def add(a, b\n    return a + b\n"

    # Valid repair -> should succeed
    valid_repaired = "def add(a, b):\n    return a + b\n"
    ok, msg = debugger.auto_repair_file("bad.py", diag, valid_repaired)
    assert ok is True
    assert bad_file.read_text(encoding="utf-8") == valid_repaired


def test_qa_engine_test_generator_and_static_analysis(temp_workspace):
    qa = QAEngine(temp_workspace)

    module_file = temp_workspace / "calculator.py"
    module_file.write_text(
        "class Calculator:\n    def add(self, a, b):\n        return a + b\n\ndef multiply(x, y):\n    return x * y\n",
        encoding="utf-8",
    )

    # Generate unit tests
    ok, test_code = qa.generate_unit_tests("calculator.py")
    assert ok is True
    assert "test_multiply_basic" in test_code
    assert "test_Calculator_instantiation" in test_code

    # Static analysis
    valid, report = qa.run_static_analysis()
    assert valid is True
    assert report["syntax_valid"] is True
    assert len(report["syntax_errors"]) == 0
