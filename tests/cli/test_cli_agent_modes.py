"""Regression tests verifying file creation and tool dispatch consistency across both CLI modes:
1. `smartai do` (one-shot autonomous mode)
2. `smartai chat` (interactive agent mode)
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
from typer.testing import CliRunner

from smart_ai_cli.agent_runner import AutonomousAgentRunner
from smart_ai_cli.client import GatewayClient
from smart_ai_cli.main import app
from smart_ai_cli.tools import write_file, edit_file, execute_tool

runner = CliRunner()


def test_do_mode_file_creation(tmp_path, monkeypatch):
    """Verifies that 'smartai do' creates files on disk with tool dispatch and verification."""
    target_file = tmp_path / "hello.md"

    def mock_chat(self, messages, tools=None, policy="adaptive", temperature=0.2):
        # Step 1: Model invokes write_file
        if len(messages) == 2:
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Creating hello.md now...",
                            "tool_calls": [
                                {
                                    "id": "call_do_01",
                                    "function": {
                                        "name": "write_file",
                                        "arguments": json.dumps(
                                            {"path": "hello.md", "content": "# Hello from Do Command\n"}
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ],
                "routing": {"tier": "cheap", "policy": policy},
                "usage": {"total_tokens": 20},
            }
        # Step 2: Model finishes after tool execution
        return {
            "choices": [
                {
                    "message": {
                        "content": "The file hello.md has been created successfully.",
                        "tool_calls": None,
                    }
                }
            ],
            "routing": {"tier": "cheap", "policy": policy},
            "usage": {"total_tokens": 25},
        }

    monkeypatch.setattr(GatewayClient, "chat", mock_chat)

    res = runner.invoke(app, ["do", "Create a hello.md in the current folder", "--cwd", str(tmp_path)])
    assert res.exit_code == 0
    assert target_file.exists()
    assert "# Hello from Do Command" in target_file.read_text(encoding="utf-8")


def test_chat_interactive_mode_file_creation(tmp_path, monkeypatch):
    """Verifies that interactive 'smartai chat' creates files on disk with tool dispatch."""
    target_file = tmp_path / "hello.md"

    def mock_chat(self, messages, tools=None, policy="adaptive", temperature=0.2):
        # If tool output was fed back, model provides final confirmation
        if any(m.get("role") == "tool" for m in messages):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "I have created hello.md in your current folder.",
                            "tool_calls": None,
                        }
                    }
                ],
                "routing": {"tier": "cheap", "policy": policy},
                "usage": {"total_tokens": 30},
            }
        # Otherwise, model issues write_file tool call
        return {
            "choices": [
                {
                    "message": {
                        "content": "Creating hello.md on disk...",
                        "tool_calls": [
                            {
                                "id": "call_chat_01",
                                "function": {
                                    "name": "write_file",
                                    "arguments": json.dumps(
                                        {"path": "hello.md", "content": "# Hello from Interactive Chat\n"}
                                    ),
                                },
                            }
                        ],
                    }
                }
            ],
            "routing": {"tier": "cheap", "policy": policy},
            "usage": {"total_tokens": 20},
        }

    monkeypatch.setattr(GatewayClient, "chat", mock_chat)
    monkeypatch.chdir(tmp_path)

    res = runner.invoke(app, ["chat", "--no-stream"], input="Create a hello.md in the current folder\n/exit\n")
    assert res.exit_code == 0
    assert target_file.exists()
    assert "# Hello from Interactive Chat" in target_file.read_text(encoding="utf-8")
    assert "Successfully created hello.md" in res.stdout


def test_chat_interactive_multiturn_sequential_tools(tmp_path, monkeypatch):
    """Verifies interactive multi-turn session creates a file in turn 1 and edits it in turn 2."""
    target_file = tmp_path / "notes.txt"

    def mock_chat(self, messages, tools=None, policy="adaptive", temperature=0.2):
        last_user = [m for m in messages if m.get("role") == "user"][-1]["content"]

        # Turn 1: Create file
        if "create" in last_user.lower():
            if any(m.get("role") == "tool" and "notes.txt" in str(m.get("content")) for m in messages):
                return {
                    "choices": [{"message": {"content": "File notes.txt has been created.", "tool_calls": None}}],
                    "routing": {"tier": "cheap", "policy": policy},
                    "usage": {"total_tokens": 15},
                }
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Writing notes.txt...",
                            "tool_calls": [
                                {
                                    "id": "call_turn1",
                                    "function": {
                                        "name": "write_file",
                                        "arguments": json.dumps(
                                            {"path": "notes.txt", "content": "Initial Content"}
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ],
                "routing": {"tier": "cheap", "policy": policy},
                "usage": {"total_tokens": 20},
            }

        # Turn 2: Edit file
        if "edit" in last_user.lower() or "update" in last_user.lower():
            if any(m.get("role") == "tool" and "updated" in str(m.get("content")).lower() for m in messages):
                return {
                    "choices": [{"message": {"content": "File notes.txt has been updated.", "tool_calls": None}}],
                    "routing": {"tier": "cheap", "policy": policy},
                    "usage": {"total_tokens": 15},
                }
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Editing notes.txt...",
                            "tool_calls": [
                                {
                                    "id": "call_turn2",
                                    "function": {
                                        "name": "edit_file",
                                        "arguments": json.dumps(
                                            {
                                                "path": "notes.txt",
                                                "target": "Initial Content",
                                                "replacement": "Updated Content",
                                            }
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ],
                "routing": {"tier": "cheap", "policy": policy},
                "usage": {"total_tokens": 25},
            }

        return {
            "choices": [{"message": {"content": "Understood.", "tool_calls": None}}],
            "routing": {"tier": "cheap", "policy": policy},
            "usage": {"total_tokens": 10},
        }

    monkeypatch.setattr(GatewayClient, "chat", mock_chat)
    monkeypatch.chdir(tmp_path)

    chat_input = (
        "create notes.txt with Initial Content\n"
        "edit notes.txt and change to Updated Content\n"
        "/exit\n"
    )
    res = runner.invoke(app, ["chat", "--no-stream"], input=chat_input)
    assert res.exit_code == 0
    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == "Updated Content"


def test_shared_tools_verification_guarantee(tmp_path):
    """Verifies that write_file and edit_file perform post-execution disk checks."""
    file_path = tmp_path / "verify_test.txt"

    # 1. Write file
    ok, msg = write_file(str(file_path), "Testing verification")
    assert ok is True
    assert file_path.exists()
    assert "Successfully created" in msg

    # 2. Edit file successfully
    ok, msg = edit_file(str(file_path), "Testing", "Verified")
    assert ok is True
    assert "Successfully updated" in msg
    assert file_path.read_text() == "Verified verification"

    # 3. Edit file fails when target text is missing
    ok, msg = edit_file(str(file_path), "NonExistentString", "Replacement")
    assert ok is False
    assert "not found" in msg
