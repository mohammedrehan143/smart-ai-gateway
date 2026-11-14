"""Cost analytics command: smartai cost."""

from __future__ import annotations

import json
import time
from typing import Optional
import typer
from rich.table import Table
from smart_ai_cli.client import GatewayClient, GatewayClientError
from smart_ai_cli.ui import console, print_error, print_status_card

app = typer.Typer(help="Inspect API expenditures, cost provenance, and model spending.")


@app.command("cost")
def cost_cmd(
    hours: Optional[float] = typer.Option(None, "--hours", "-h", help="Filter cost within last N hours"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output raw JSON format"),
) -> None:
    """Displays total spending, model-level cost distribution, and rate-card cost provenance."""
    client = GatewayClient()

    since_ts: Optional[float] = None
    if hours:
        since_ts = time.time() - (hours * 3600)

    try:
        cost = client.get_cost(since=since_ts)

        if json_output:
            console.print_json(json.dumps(cost.model_dump()))
            return

        # 1. Spend Overview Card
        print_status_card(
            "Gateway Expenditure Overview",
            {
                "Total Expenditure": f"[bold cyan]${cost.total_spend:.6f} {cost.currency}[/]",
                "Calculated Provenance": f"[bold green]${cost.calculated_spend:.6f}[/] (Verified Rate Card)",
                "Estimated Spending": f"[yellow]${cost.estimated_spend:.6f}[/]",
                "Currency": cost.currency,
            },
            border_style="green",
        )

        # 2. Model Spend Table
        if cost.model_breakdown:
            m_table = Table(title="Expenditure by Model Alias", header_style="bold cyan", border_style="dim")
            m_table.add_column("Model Alias", style="bold white")
            m_table.add_column("Spend (USD)", justify="right", style="bold cyan")
            m_table.add_column("Tokens", justify="right")
            m_table.add_column("Requests", justify="right")
            m_table.add_column("Avg Cost/Req", justify="right", style="dim")

            for model_name, summary in cost.model_breakdown.items():
                avg_cost = (summary.spend / summary.requests) if summary.requests > 0 else 0.0
                m_table.add_row(
                    model_name,
                    f"${summary.spend:.6f}",
                    f"{summary.tokens:,}",
                    f"{summary.requests:,}",
                    f"${avg_cost:.6f}",
                )
            console.print(m_table)

        # 3. Provider Spend Table
        if cost.provider_breakdown:
            p_table = Table(title="Expenditure by Upstream Provider", header_style="bold magenta", border_style="dim")
            p_table.add_column("Provider", style="bold white")
            p_table.add_column("Spend (USD)", justify="right", style="bold cyan")
            p_table.add_column("Requests", justify="right")

            for prov_name, summary in cost.provider_breakdown.items():
                p_table.add_row(
                    prov_name,
                    f"${summary.spend:.6f}",
                    f"{summary.requests:,}",
                )
            console.print(p_table)

    except GatewayClientError as exc:
        print_error(f"Failed to fetch cost analytics: {exc}")
        raise typer.Exit(code=1)
