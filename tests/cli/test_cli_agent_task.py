"""Tests for Smart AI CLI Autonomous Agent and Task execution."""

import json
from unittest.mock import MagicMock
from typer.testing import CliRunner

from smart_ai_cli.agent_runner import AutonomousAgentRunner, extract_action_blocks
from smart_ai_cli.main import app
from smart_ai_cli.tools import (
    edit_file,
    execute_tool,
    list_directory,
    read_file,
    run_command,
    write_file,
)

runner = CliRunner()


def test_write_read_edit_file_tools(tmp_path):
    target_file = tmp_path / "greeting.txt"

    # 1. Write file
    ok, msg = write_file(str(target_file), "Hello World!\nLine 2\nLine 3")
    assert ok is True
    assert target_file.exists()
    assert "Successfully created" in msg

    # 2. Read file full
    ok, content = read_file(str(target_file))
    assert ok is True
    assert "Hello World!" in content
    assert "Line 2" in content

    # 3. Read file with line range
    ok, sliced = read_file(str(target_file), start_line=2, end_line=2)
    assert ok is True
    assert "Line 2" in sliced
    assert "Hello World!" not in sliced

    # 4. Edit file
    ok, msg = edit_file(str(target_file), target="Hello World!", replacement="Hi Everyone!")
    assert ok is True
    assert "Successfully updated" in msg

    # Verify edited content
    ok, content = read_file(str(target_file))
    assert "Hi Everyone!" in content
    assert "Hello World!" not in content

    # Edit non-existent text
    ok, msg = edit_file(str(target_file), target="Missing String", replacement="Something")
    assert ok is False
    assert "not found" in msg


def test_list_directory_tool(tmp_path):
    (tmp_path / "dirA").mkdir()
    (tmp_path / "file1.txt").write_text("abc")
    (tmp_path / "file2.py").write_text("print('test')")

    ok, listing = list_directory(str(tmp_path))
    assert ok is True
    assert "[DIR]  dirA" in listing
    assert "[FILE] file1.txt" in listing
    assert "[FILE] file2.py" in listing


def test_run_command_tool():
    ok, output = run_command('python -c "print(40 + 2)"')
    assert ok is True
    assert "42" in output

    ok, output = run_command("nonexistent_command_xyz_123")
    assert ok is False


def test_extract_action_blocks():
    text = (
        "I will create the file for you now.\n"
        "```action:write_file\n"
        '{"path": "hello.py", "content": "print(\'hi\')"}\n'
        "```\n"
        "And then read it:\n"
        "```action:read_file\n"
        '{"path": "hello.py"}\n'
        "```"
    )
    blocks = extract_action_blocks(text)
    assert len(blocks) == 2
    assert blocks[0]["name"] == "write_file"
    assert blocks[0]["args"]["path"] == "hello.py"
    assert blocks[1]["name"] == "read_file"


def test_autonomous_agent_runner_with_native_tools(tmp_path):
    mock_client = MagicMock()
    # Step 1: Model requests tool call to write a file
    mock_client.chat.side_effect = [
        {
            "choices": [
                {
                    "message": {
                        "content": "Creating the script now...",
                        "tool_calls": [
                            {
                                "id": "call_01",
                                "function": {
                                    "name": "write_file",
                                    "arguments": json.dumps(
                                        {"path": str(tmp_path / "calc.py"), "content": "def add(a, b): return a + b\n"}
                                    ),
                                },
                            }
                        ],
                    }
                }
            ]
        },
        # Step 2: Model finishes with final summary
        {
            "choices": [
                {
                    "message": {
                        "content": "The file calc.py has been created with the requested addition function.",
                        "tool_calls": None,
                    }
                }
            ]
        },
    ]

    agent = AutonomousAgentRunner(client=mock_client, max_steps=5)
    res = agent.execute_task("Create calc.py with add function", cwd=str(tmp_path))

    assert res.success is True
    assert res.steps_taken == 2
    assert len(res.files_created) == 1
    assert (tmp_path / "calc.py").exists()
    assert "add(a, b)" in (tmp_path / "calc.py").read_text()


def test_cli_do_command(tmp_path, monkeypatch):
    test_file = tmp_path / "cli_test.txt"

    # Mock AutonomousAgentRunner.execute_task
    def mock_execute_task(self, task_prompt, policy, temperature, cwd):
        write_file(str(test_file), "Created by CLI do command")
        res = MagicMock()
        res.success = True
        return res

    monkeypatch.setattr(AutonomousAgentRunner, "execute_task", mock_execute_task)

    result = runner.invoke(app, ["do", f"create file {test_file}"])
    assert result.exit_code == 0
    assert test_file.exists()
    assert "Created by CLI do command" in test_file.read_text()
