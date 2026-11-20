"""Unit tests for Smart AI Git Engine."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from smart_ai_cli.git_engine import GitEngine
from smart_ai_cli.process_manager import ProcessManager


@pytest.fixture
def temp_git_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        # Initialize real git repo
        pm = ProcessManager(p)
        pm.run_command("git init", cwd=p)
        pm.run_command('git config user.name "Smart AI Agent"', cwd=p)
        pm.run_command('git config user.email "agent@smartai.internal"', cwd=p)
        yield p


def test_git_engine_operations(temp_git_workspace):
    git = GitEngine(temp_git_workspace)

    assert git.is_git_repo() is True

    # 1. Create file and check status
    f = temp_git_workspace / "main.py"
    f.write_text("print('hello git')\n", encoding="utf-8")

    ok, status = git.get_status()
    assert ok is True
    assert "main.py" in status["untracked"]

    # 2. Stage file
    ok, msg = git.stage_files(["main.py"])
    assert ok is True

    ok, status = git.get_status()
    assert "main.py" in status["staged"]

    # 3. Commit
    ok, msg = git.commit("feat: initial commit")
    assert ok is True

    # 4. Get log
    ok, logs = git.get_log(max_count=5)
    assert ok is True
    assert len(logs) >= 1
    assert "feat: initial commit" in logs[0]["message"]

    # 5. Conventional commit message generator
    diff = "def test_something():\n    assert True\n"
    msg = git.generate_conventional_commit_message(diff, "add unit test")
    assert msg.startswith("test:")

    # 6. Manage gitignore
    ok, msg = git.manage_gitignore([".env", ".smartai/"])
    assert ok is True
    gi_content = (temp_git_workspace / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gi_content
    assert ".smartai/" in gi_content
