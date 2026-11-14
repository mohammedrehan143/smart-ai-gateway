"""Unit tests for CLI configuration management."""

from pathlib import Path
from typer.testing import CliRunner
from smart_ai_cli.config import ConfigManager
from smart_ai_cli.main import app

runner = CliRunner()


def test_config_manager_lifecycle(tmp_path: Path):
    cfg_file = tmp_path / "config.json"
    mgr = ConfigManager(config_path=cfg_file)

    cfg = mgr.load_config()
    assert cfg.default_policy == "adaptive"
    assert cfg.default_temperature == 0.2

    # Update value
    mgr.set("default_policy", "always_strong")
    assert mgr.get("default_policy") == "always_strong"

    # Reload from disk
    mgr2 = ConfigManager(config_path=cfg_file)
    assert mgr2.get("default_policy") == "always_strong"


def test_cli_config_commands():
    # View configuration
    res1 = runner.invoke(app, ["config"])
    assert res1.exit_code == 0
    assert "Smart AI CLI Configuration" in res1.stdout

    # Get single key
    res2 = runner.invoke(app, ["config", "default_policy"])
    assert res2.exit_code == 0
    assert "default_policy:" in res2.stdout

    # Set valid key
    res3 = runner.invoke(app, ["config", "default_policy", "always_cheap"])
    assert res3.exit_code == 0
    assert "Updated" in res3.stdout

    # Reset
    res4 = runner.invoke(app, ["config", "reset"])
    assert res4.exit_code == 0
    assert "reset to default" in res4.stdout
