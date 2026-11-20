"""Unit tests for Smart AI Process Execution Engine."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
import pytest

from smart_ai_cli.process_manager import ProcessManager
from smart_ai_cli.tools import execute_tool


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_process_manager_run_command_and_script(temp_workspace):
    pm = ProcessManager(temp_workspace)

    # 1. Run command
    cmd = f'"{sys.executable}" -c "print(12345 + 54321)"'
    success, output, code = pm.run_command(cmd)
    assert success is True
    assert code == 0
    assert "66666" in output

    # 2. Run script
    script_file = temp_workspace / "calc.py"
    script_file.write_text("import sys\nprint('ARGS:', sys.argv[1:])\n", encoding="utf-8")

    success, output, code = pm.run_script("calc.py", args=["alpha", "beta"], cwd=temp_workspace)
    assert success is True
    assert code == 0
    assert "['alpha', 'beta']" in output


def test_process_manager_background_process_lifecycle(temp_workspace):
    pm = ProcessManager(temp_workspace)

    try:
        # Start long-running script in background
        cmd = f"\"{sys.executable}\" -u -c \"import time; print('server starting', flush=True); time.sleep(10); print('server done', flush=True)\""
        ok, msg, proc_id = pm.start_background_process(cmd, process_name="test_worker", cwd=temp_workspace)
        assert ok is True
        assert proc_id == "test_worker"

        # Give process brief moment to initialize
        time.sleep(0.5)

        # Check status
        ok, status = pm.get_process_status("test_worker")
        assert ok is True
        assert status["is_running"] is True
        assert "server starting" in status["recent_logs"]

        # List processes
        procs = pm.list_background_processes()
        assert any(p["id"] == "test_worker" for p in procs)

        # Stop process
        ok, msg = pm.stop_background_process("test_worker")
        assert ok is True

        # Check status after stop
        ok, status = pm.get_process_status("test_worker")
        assert ok is True
        assert status["is_running"] is False
    finally:
        pm.stop_all()


def test_process_manager_parallel_and_ports(temp_workspace):
    pm = ProcessManager(temp_workspace)

    # Parallel commands
    cmds = [
        f'"{sys.executable}" -c "print(\'T1\')"',
        f'"{sys.executable}" -c "print(\'T2\')"',
        f'"{sys.executable}" -c "print(\'T3\')"',
    ]
    results = pm.run_parallel_commands(cmds, cwd=temp_workspace)
    assert len(results) == 3
    for r in results:
        assert r["success"] is True

    # Executable discovery
    discovered = pm.discover_executables(["python"])
    assert "python" in discovered

    # Available port discovery
    port = pm.find_available_port(start_port=18000)
    assert port is not None
    assert 18000 <= port < 18100


def test_tools_dispatch_process(temp_workspace):
    cmd = f'"{sys.executable}" -c "print(\'AGENT_TOOL_SUCCESS\')"'
    ok, out = execute_tool("run_command", {"command": cmd}, cwd=temp_workspace)
    assert ok is True
    assert "AGENT_TOOL_SUCCESS" in out
