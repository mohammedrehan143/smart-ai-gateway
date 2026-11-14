"""Usage analytics command: smartai usage."""

from __future__ import annotations

import json
import time
from typing import Optional
import typer
from rich.table import Table
from smart_ai_cli.client import GatewayClient, GatewayClientError
from smart_ai_cli.ui import console, print_error, print_status_card

app = typer.Typer(help="View request volume, token usage, and latency analytics.")


@app.command("usage")
def usage_cmd(
    limit: int = typer.Option(10, "--limit", "-l", help="Number of recent requests to display"),
    hours: Optional[float] = typer.Option(None, "--hours", "-h", help="Filter usage within last N hours"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output raw JSON format"),
) -> None:
    """Displays gateway usage metrics including token counts, average latency, and cache hits."""
    client = GatewayClient()

    since_ts: Optional[float] = None
    if hours:
        since_ts = time.time() - (hours * 3600)

    try:
        usage = client.get_usage(since=since_ts, limit=limit)

        if json_output:
            console.print_json(json.dumps(usage.model_dump()))
            return

        # 1. Summary Card
        cache_pct = f"{usage.cache_hit_rate * 100:.1f}%"
        print_status_card(
            "Gateway Usage Overview",
            {
                "Total Requests": f"[bold white]{usage.total_requests:,}[/]",
                "Total Tokens": f"[bold cyan]{usage.total_tokens:,}[/] (In: {usage.total_input_tokens:,} | Out: {usage.total_output_tokens:,})",
                "Average Latency": f"[yellow]{usage.avg_latency_ms:.1f}ms[/]",
                "Cache Hit Rate": f"[green]{cache_pct}[/] ({usage.cache_hits} hits)",
                "Fallbacks Triggered": f"[magenta]{usage.fallback_count}[/]",
            },
            border_style="cyan",
        )

        # 2. Policy Distribution Table
        if usage.policy_breakdown:
            p_table = Table(title="Policy Distribution", header_style="bold yellow", border_style="dim")
            p_table.add_column("Routing Policy")
            p_table.add_column("Requests", justify="right")
            p_table.add_column("Share", justify="right")

            for pol, count in usage.policy_breakdown.items():
                share = (count / usage.total_requests * 100) if usage.total_requests > 0 else 0.0
                p_table.add_row(pol, f"{count:,}", f"{share:.1f}%")

            console.print(p_table)

        # 3. Recent Requests Table
        if usage.recent_requests:
            r_table = Table(title=f"Recent Request Activity (Last {len(usage.recent_requests)})", header_style="bold cyan", border_style="dim")
            r_table.add_column("Trace ID", style="dim")
            r_table.add_column("Policy", style="yellow")
            r_table.add_column("Model", style="bold white")
            r_table.add_column("Status")
            r_table.add_column("Latency", justify="right")
            r_table.add_column("Cached", justify="center")

            for req in usage.recent_requests:
                status_color = "green" if req.get("status") == "success" else "red"
                cached_badge = "[bold blue]YES[/]" if req.get("cached") else "[dim]NO[/]"
                r_table.add_row(
                    str(req.get("trace_id", ""))[:18],
                    str(req.get("policy", "")),
                    str(req.get("model", "")),
                    f"[{status_color}]{req.get('status', '')}[/]",
                    f"{req.get('latency_ms', 0)}ms",
                    cached_badge,
                )
            console.print(r_table)

    except GatewayClientError as exc:
        print_error(f"Failed to fetch usage analytics: {exc}")
        raise typer.Exit(code=1)
