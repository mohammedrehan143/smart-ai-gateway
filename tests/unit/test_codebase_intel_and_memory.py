"""Unit tests for Codebase Intelligence and Project Memory engines."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from smart_ai_cli.codebase_intel import CodebaseIntelligence
from smart_ai_cli.project_memory import ProjectMemoryManager


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_codebase_intelligence_metrics_and_frameworks(temp_workspace):
    intel = CodebaseIntelligence(temp_workspace)

    # Create dummy files
    (temp_workspace / "app.py").write_text("import fastapi\nprint('hello')\n", encoding="utf-8")
    (temp_workspace / "requirements.txt").write_text("fastapi>=0.100.0\npytest>=8.0.0\n", encoding="utf-8")

    metrics = intel.scan_project_metrics()
    assert metrics["total_files"] >= 2
    assert "Python" in metrics["language_file_counts"]
    assert "FastAPI" in metrics["detected_frameworks"]
    assert "Pytest" in metrics["detected_frameworks"]


def test_codebase_intelligence_circular_dependency(temp_workspace):
    intel = CodebaseIntelligence(temp_workspace)

    # Create circular import: mod_a imports mod_b, mod_b imports mod_a
    (temp_workspace / "mod_a.py").write_text("import mod_b\ndef func_a(): pass\n", encoding="utf-8")
    (temp_workspace / "mod_b.py").write_text("import mod_a\ndef func_b(): pass\n", encoding="utf-8")

    cycles = intel.detect_circular_dependencies()
    assert len(cycles) > 0
    cycle_nodes = [Path(p).stem for p in cycles[0]]
    assert "mod_a" in cycle_nodes and "mod_b" in cycle_nodes

    mermaid = intel.generate_mermaid_diagram()
    assert "flowchart TD" in mermaid
    assert "mod_a" in mermaid
    assert "mod_b" in mermaid


def test_project_memory_lifecycle(temp_workspace):
    mem = ProjectMemoryManager(temp_workspace)

    # 1. Record modification
    mem.record_modification("src/auth.py", "Added JWT verification function")

    # 2. Record error resolution
    mem.record_error_resolution(
        error_type="ModuleNotFoundError",
        root_cause="Missing redis package",
        fix_summary="Ran pip install redis and updated requirements.txt",
    )

    # 3. Add user instruction
    mem.add_user_instruction("Always run pytest with -q flag")

    # 4. Search solution
    found = mem.search_error_solution("ModuleNotFoundError: No module named 'redis'")
    assert found is not None
    assert "pip install redis" in found["fix_summary"]

    # 5. Check memory context injection
    ctx = mem.get_memory_context()
    assert "Always run pytest with -q flag" in ctx
    assert "src/auth.py" in ctx

    # 6. Reload from disk to verify persistence
    mem2 = ProjectMemoryManager(temp_workspace)
    assert len(mem2.get_user_instructions()) == 1
    assert mem2.get_user_instructions()[0] == "Always run pytest with -q flag"
