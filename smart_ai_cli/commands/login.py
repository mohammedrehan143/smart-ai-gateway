"""Authentication commands: smartai login & smartai logout."""

from __future__ import annotations

import typer
from rich.prompt import Prompt
from smart_ai_cli.auth import default_auth_manager
from smart_ai_cli.client import AuthenticationError, GatewayClient, GatewayConnectionError
from smart_ai_cli.config import default_config_manager
from smart_ai_cli.ui import console, print_error, print_status_card, print_success

app = typer.Typer(help="Authenticate and manage credentials.")


@app.command("login")
def login_cmd(
    url: str = typer.Option(None, "--url", "-u", help="Gateway Base URL (e.g. https://smart-ai-gateway.onrender.com)"),
    key: str = typer.Option(None, "--key", "-k", help="Gateway API Key (optional non-interactive)"),
) -> None:
    """Authenticates with the Smart AI Gateway and stores credentials in OS Keyring."""
    cfg = default_config_manager.load_config()
    target_url = url or cfg.gateway_url

    if not url:
        prompt_url = Prompt.ask(
            "[bold white]Enter Gateway URL[/bold white]",
            default=target_url,
        )
        target_url = prompt_url.strip()

    if not key:
        api_key = Prompt.ask(
            "[bold white]Enter Gateway API Key (leave empty for open demo mode)[/bold white]",
            password=True,
            default="",
        ).strip()
    else:
        api_key = key.strip()

    console.print(f"[dim]Connecting to {target_url}...[/dim]")
    client = GatewayClient(base_url=target_url, api_key=api_key if api_key else None)

    try:
        # Check liveness and verify auth
        live_info = client.health_live()
        auth_info = client.verify_auth()

        # Update config & keyring
        default_config_manager.set("gateway_url", target_url)
        if api_key:
            default_auth_manager.set_api_key(api_key)
            cred_status = "Stored in OS Keyring (Secure)"
        else:
            default_auth_manager.delete_api_key()
            cred_status = "Open / Unrestricted Access Mode"

        print_success("Authenticated with Smart AI Gateway successfully!")
        print_status_card(
            "Session Connection Profile",
            {
                "Gateway URL": target_url,
                "Version": live_info.get("gateway_version", "0.1.0"),
                "Environment": live_info.get("environment", "production"),
                "Auth Enforcement": "Required" if auth_info.auth_enforced else "Optional / Open Mode",
                "Credentials": cred_status,
            },
            border_style="green",
        )
    except AuthenticationError as exc:
        print_error(f"Authentication failed: {exc}", hint="Verify your gateway key or check environment settings.")
        raise typer.Exit(code=1)
    except GatewayConnectionError as exc:
        print_error(f"Connection error: {exc}", hint=f"Ensure {target_url} is reachable.")
        raise typer.Exit(code=1)
    except Exception as exc:
        print_error(f"Unexpected error during login: {exc}")
        raise typer.Exit(code=1)


@app.command("logout")
def logout_cmd() -> None:
    """Removes stored Gateway credentials from the operating system keyring."""
    if default_auth_manager.has_api_key():
        default_auth_manager.delete_api_key()
        print_success("Logged out successfully. Credentials removed from OS Keyring.")
    else:
        console.print("[dim]No active credentials found in Keyring.[/dim]")
