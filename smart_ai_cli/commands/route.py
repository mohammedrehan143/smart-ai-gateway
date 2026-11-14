"""Routing inspection command: smartai route."""

from __future__ import annotations

import json
from typing import Optional
import typer
from rich.table import Table
from smart_ai_cli.client import GatewayClient, GatewayClientError
from smart_ai_cli.ui import console, print_error, render_cost_badge, render_tier_badge

app = typer.Typer(help="Inspect recent deterministic routing decisions and feature extractions.")


@app.command("route")
def route_cmd(
    limit: int = typer.Option(10, "--limit", "-l", help="Number of recent decisions to inspect"),
    trace: Optional[str] = typer.Option(None, "--trace", "-t", help="Filter by specific Trace ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output raw JSON format"),
) -> None:
    """Displays auto-routing decisions, tier selections, classification reasons, and feature tags."""
    client = GatewayClient()

    try:
        decisions_resp = client.get_routing_decisions(limit=limit, trace_id=trace)
        records = decisions_resp.decisions

        if json_output:
            console.print_json(json.dumps([r.model_dump() for r in records]))
            return

        if not records:
            console.print("[dim]No routing decisions recorded yet.[/dim]")
            return

        table = Table(
            title=f"Recent Intelligent Routing Decisions ({len(records)} Records)",
            header_style="bold cyan",
            border_style="dim",
        )
        table.add_column("Trace ID", style="dim")
        table.add_column("Policy", style="yellow")
        table.add_column("Tier")
        table.add_column("Selected Model", style="bold white")
        table.add_column("Extracted Features", style="cyan")
        table.add_column("Routing Reason", style="white")
        table.add_column("Cost (USD)", justify="right")
        table.add_column("Latency", justify="right")

        for r in records:
            # Format feature tags (e.g. code:+, debug:-, multi:-)
            feats = r.features or {}
            feat_parts = []
            if feats.get("has_code"):
                feat_parts.append("[bold green]code[/]")
            if feats.get("has_debug"):
                feat_parts.append("[bold magenta]debug[/]")
            if feats.get("is_multistep"):
                feat_parts.append("[bold yellow]multi-step[/]")
            if not feat_parts:
                feat_parts.append("[dim]routine[/]")
            feat_str = " ".join(feat_parts)

            cost_badge = render_cost_badge(r.cost_estimate)
            table.add_row(
                r.trace_id[:16],
                r.policy,
                render_tier_badge(r.tier),
                r.selected_model,
                feat_str,
                r.reason[:55] + "..." if len(r.reason) > 55 else r.reason,
                cost_badge,
                f"{r.latency_ms}ms",
            )

        console.print(table)
    except GatewayClientError as exc:
        print_error(f"Failed to inspect routing decisions: {exc}")
        raise typer.Exit(code=1)
