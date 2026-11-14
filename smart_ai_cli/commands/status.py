"""Status command: smartai status."""

from __future__ import annotations

import time
import typer
from smart_ai_cli.auth import default_auth_manager
from smart_ai_cli.client import GatewayClient, GatewayConnectionError
from smart_ai_cli.config import default_config_manager
from smart_ai_cli.ui import console, print_error, print_status_card

app = typer.Typer(help="Check gateway connection and platform health.")


@app.command("status")
def status_cmd() -> None:
    """Checks Smart AI Gateway connectivity, readiness, database status, and latency."""
    cfg = default_config_manager.load_config()
    client = GatewayClient()

    console.print(f"[dim]Pinging Gateway at {cfg.gateway_url}...[/dim]")
    start = time.time()
    try:
        live_res = client.health_live()
        ready_res = client.health_ready()
        elapsed_ms = round((time.time() - start) * 1000, 1)

        has_key = default_auth_manager.has_api_key()
        cred_indicator = "[bold green]Configured (Keyring)[/]" if has_key else "[dim]Unrestricted / Open Demo[/]"

        print_status_card(
            "Smart AI Gateway Status",
            {
                "Gateway URL": cfg.gateway_url,
                "Health Live": f"[bold green]{live_res.get('status', 'online')}[/]",
                "Health Ready": f"[bold green]{ready_res.get('status', 'ready')}[/]",
                "Database": f"[bold cyan]{ready_res.get('database', 'connected')}[/]",
                "Gateway Version": live_res.get("gateway_version", "0.1.0"),
                "Environment": live_res.get("environment", "production"),
                "API Key Auth": cred_indicator,
                "Ping Latency": f"[cyan]{elapsed_ms}ms[/]",
                "Default Policy": f"[yellow]{cfg.default_policy}[/]",
            },
            border_style="cyan",
        )
    except GatewayConnectionError as exc:
        print_error(f"Gateway Unreachable: {exc}", hint=f"Check if {cfg.gateway_url} is online and accessible.")
        raise typer.Exit(code=1)
    except Exception as exc:
        print_error(f"Status check failed: {exc}")
        raise typer.Exit(code=1)
