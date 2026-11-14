"""Models command: smartai models."""

from __future__ import annotations

import json
import typer
from rich.table import Table
from smart_ai_cli.client import GatewayClient, GatewayClientError
from smart_ai_cli.ui import console, print_error, render_tier_badge

app = typer.Typer(help="List and inspect registered models and rate cards.")


@app.command("models")
def models_cmd(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output raw JSON format"),
    tier_filter: str = typer.Option(None, "--tier", "-t", help="Filter by tier: cheap or strong"),
) -> None:
    """Lists registered AI models, provider metadata, context limits, and rate cards."""
    client = GatewayClient()

    try:
        models_resp = client.list_models()
        data = models_resp.data

        if tier_filter:
            data = [m for m in data if m.tier.lower() == tier_filter.lower()]

        if json_output:
            console.print_json(json.dumps([m.model_dump() for m in data]))
            return

        table = Table(
            title=f"Smart AI Gateway Models Catalog ({len(data)} Models)",
            header_style="bold cyan",
            border_style="dim",
        )
        table.add_column("Alias", style="bold white")
        table.add_column("Provider", style="cyan")
        table.add_column("Tier")
        table.add_column("Context Win", justify="right")
        table.add_column("Max Output", justify="right")
        table.add_column("Input / 1M", justify="right")
        table.add_column("Output / 1M", justify="right")
        table.add_column("Tools", justify="center")
        table.add_column("Status", justify="center")

        for m in data:
            status_text = "[bold green]Active[/]" if m.is_active else "[red]Inactive[/]"
            tools_text = "[green]✔[/]" if m.supports_tools else "[dim]✖[/]"
            in_rate = f"${m.pricing.input_rate_per_million:.2f}"
            out_rate = f"${m.pricing.output_rate_per_million:.2f}"

            table.add_row(
                m.alias,
                m.provider,
                render_tier_badge(m.tier),
                f"{m.context_window:,}",
                f"{m.max_output_tokens:,}",
                in_rate,
                out_rate,
                tools_text,
                status_text,
            )

        console.print(table)
    except GatewayClientError as exc:
        print_error(f"Failed to list models: {exc}")
        raise typer.Exit(code=1)
