"""Configuration management command: smartai config."""

from __future__ import annotations

from typing import Any, Optional
import typer
from smart_ai_cli.config import CONFIG_FILE, default_config_manager
from smart_ai_cli.schemas import GatewayConfig
from smart_ai_cli.ui import console, print_error, print_status_card, print_success

app = typer.Typer(help="Inspect and update CLI configuration settings.")


@app.callback(invoke_without_command=True)
def config_cmd(
    ctx: typer.Context,
    key: Optional[str] = typer.Argument(None, help="Config key to inspect or set"),
    value: Optional[str] = typer.Argument(None, help="New value for the config key"),
) -> None:
    """Displays or updates CLI preferences (~/.smartai/config.json)."""
    if ctx.invoked_subcommand is not None:
        return

    # Check for reset keyword
    if key == "reset":
        reset_config_cmd()
        return

    # If key and value provided, set value
    if key and value:
        _set_config_value(key, value)
        return

    # If only key provided, get value
    if key and not value:
        try:
            val = default_config_manager.get(key)
            console.print(f"[bold cyan]{key}:[/] {val}")
        except KeyError as exc:
            print_error(str(exc))
        return

    # Otherwise display complete configuration
    cfg = default_config_manager.load_config()
    print_status_card(
        "Smart AI CLI Configuration",
        {
            "Config File": str(CONFIG_FILE),
            "gateway_url": cfg.gateway_url,
            "default_policy": cfg.default_policy,
            "default_temperature": cfg.default_temperature,
            "timeout_seconds": f"{cfg.timeout_seconds}s",
            "stream_output": cfg.stream_output,
        },
        border_style="cyan",
    )


def _set_config_value(key: str, value: str) -> None:
    try:
        # Cast value according to target schema type
        if key in ("default_temperature", "timeout_seconds"):
            parsed_val: Any = float(value)
        elif key == "stream_output":
            parsed_val = value.lower() in ("true", "1", "yes")
        elif key == "default_policy":
            if value not in ("adaptive", "always_cheap", "always_strong"):
                print_error("Policy must be one of: 'adaptive', 'always_cheap', 'always_strong'")
                raise typer.Exit(code=1)
            parsed_val = value
        else:
            parsed_val = value

        default_config_manager.set(key, parsed_val)
        print_success(f"Updated [bold cyan]{key}[/] = {parsed_val}")
    except KeyError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)
    except ValueError as exc:
        print_error(f"Invalid value for {key}: {exc}")
        raise typer.Exit(code=1)


@app.command("reset")
def reset_config_cmd() -> None:
    """Resets configuration to original defaults."""
    default_config_manager.save_config(GatewayConfig())
    print_success("Configuration reset to default settings.")
