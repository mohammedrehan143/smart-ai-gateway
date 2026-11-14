"""Unit and integration tests for CLI Authentication and Credential Security."""

from pathlib import Path
from typer.testing import CliRunner
from smart_ai_cli.auth import AuthManager
from smart_ai_cli.main import app

runner = CliRunner()


def test_auth_manager_storage(tmp_path: Path):
    auth_file = tmp_path / "credentials.json"
    mgr = AuthManager(service_name="test_smartai", username="test_user")
    mgr.fallback_file = auth_file

    assert mgr.get_api_key() is None
    assert mgr.has_api_key() is False

    # Store key
    mgr.set_api_key("gw_secret_test_key_12345")
    assert mgr.has_api_key() is True
    assert mgr.get_api_key() == "gw_secret_test_key_12345"

    # Delete key
    mgr.delete_api_key()
    assert mgr.has_api_key() is False
    assert mgr.get_api_key() is None


def test_cli_logout_command():
    res = runner.invoke(app, ["logout"])
    assert res.exit_code == 0


def test_cli_login_masked_credential(monkeypatch):
    # Ensure secret credentials are never leaked into stdout/stderr
    secret_key = "super_confidential_token_xyz"
    runner_res = runner.invoke(
        app,
        ["login", "--url", "http://localhost:8000", "--key", secret_key],
    )
    # Output must NEVER print the raw secret key
    assert secret_key not in runner_res.stdout
