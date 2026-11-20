"""Unit tests for Smart AI Filesystem Engine and FileHistoryManager."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from smart_ai_cli.file_history import FileHistoryManager
from smart_ai_cli.filesystem import WorkspaceFilesystem
from smart_ai_cli.tools import execute_tool


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_file_history_manager_snapshot_and_rollback(temp_workspace):
    history = FileHistoryManager(temp_workspace)
    test_file = temp_workspace / "sample.txt"
    test_file.write_text("Version 1 content", encoding="utf-8")

    snap1 = history.snapshot(test_file, description="initial")
    assert snap1 is not None

    test_file.write_text("Version 2 content with modifications", encoding="utf-8")
    snap2 = history.snapshot(test_file, description="second")
    assert snap2 is not None

    # Verify diff
    ok, diff = history.get_diff(test_file, snap1)
    assert ok is True
    assert "-Version 1 content" in diff
    assert "+Version 2 content with modifications" in diff

    # Rollback to snap1
    ok, msg = history.rollback(test_file, snap1)
    assert ok is True
    assert test_file.read_text(encoding="utf-8") == "Version 1 content"


def test_workspace_fs_crud_and_snapshots(temp_workspace):
    fs = WorkspaceFilesystem(temp_workspace)

    # 1. Write file
    ok, msg = fs.write_file("nested/test.py", "print('hello world')")
    assert ok is True
    target = temp_workspace / "nested" / "test.py"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "print('hello world')"

    # 2. Read file
    ok, content = fs.read_file("nested/test.py")
    assert ok is True
    assert "print('hello world')" in content

    # 3. Edit file
    ok, msg = fs.edit_file("nested/test.py", "hello world", "smart ai")
    assert ok is True
    assert target.read_text(encoding="utf-8") == "print('smart ai')"

    # 4. Copy file
    ok, msg = fs.copy_file("nested/test.py", "nested/test_copy.py")
    assert ok is True
    copy_target = temp_workspace / "nested" / "test_copy.py"
    assert copy_target.exists()
    assert copy_target.read_text(encoding="utf-8") == "print('smart ai')"

    # 5. Rename file
    ok, msg = fs.rename_file("nested/test_copy.py", "nested/test_renamed.py")
    assert ok is True
    assert not copy_target.exists()
    assert (temp_workspace / "nested" / "test_renamed.py").exists()

    # 6. Delete file (snapshots before deletion)
    ok, msg = fs.delete_file("nested/test_renamed.py")
    assert ok is True
    assert not (temp_workspace / "nested" / "test_renamed.py").exists()

    # 7. Rollback deleted file
    ok, msg = fs.rollback("nested/test_renamed.py")
    assert ok is True
    assert (temp_workspace / "nested" / "test_renamed.py").exists()


def test_workspace_fs_directory_and_search_operations(temp_workspace):
    fs = WorkspaceFilesystem(temp_workspace)

    # Create directories
    ok, msg = fs.create_directory("src/components")
    assert ok is True
    assert (temp_workspace / "src" / "components").is_dir()

    # Batch write files
    files = [
        {
            "path": "src/components/Header.jsx",
            "content": "export function Header() { return <header>Header</header>; }",
        },
        {
            "path": "src/components/Footer.jsx",
            "content": "export function Footer() { return <footer>Footer</footer>; }",
        },
        {
            "path": "src/utils.js",
            "content": "export function calculateTotal(items) { return items.reduce((a, b) => a + b, 0); }",
        },
    ]
    ok, msg = fs.batch_write_files(files)
    assert ok is True

    # Find files glob
    ok, msg = fs.find_files("*.jsx")
    assert ok is True
    assert "Header.jsx" in msg
    assert "Footer.jsx" in msg
    assert "utils.js" not in msg

    # Search in files
    ok, msg = fs.search_in_files("calculateTotal")
    assert ok is True
    assert "utils.js:1:" in msg

    # List directory
    ok, msg = fs.list_directory("src", recursive=True)
    assert ok is True
    assert "Header.jsx" in msg
    assert "Footer.jsx" in msg


def test_tools_dispatch_filesystem(temp_workspace):
    # Test execute_tool wrapper with filesystem commands
    ok, res = execute_tool("write_file", {"path": "hello.txt", "content": "Hello Autonomous Agent"}, cwd=temp_workspace)
    assert ok is True
    assert (temp_workspace / "hello.txt").exists()

    ok, res = execute_tool("read_file", {"path": "hello.txt"}, cwd=temp_workspace)
    assert ok is True
    assert "Hello Autonomous Agent" in res

    ok, res = execute_tool("find_files", {"pattern": "*.txt"}, cwd=temp_workspace)
    assert ok is True
    assert "hello.txt" in res
