"""Benchmark command: smartai benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
import typer
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from smart_ai_cli.client import GatewayClient, GatewayClientError
from smart_ai_cli.ui import console, print_error, print_status_card, print_success

app = typer.Typer(help="Execute multi-policy evaluations and benchmark cost savings.")


@app.command("benchmark")
def benchmark_cmd(
    sample_size: int = typer.Option(5, "--samples", "-s", help="Number of benchmark tasks to run (1-21)"),
    export: Optional[Path] = typer.Option(
        None, "--export", "-e", help="Export benchmark results to file (.json or .md)"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output raw JSON format"),
) -> None:
    """Runs evaluation benchmark tasks across policies (adaptive, always_cheap, always_strong)."""
    client = GatewayClient()

    policies = ["adaptive", "always_cheap", "always_strong"]
    console.print(
        f"[bold cyan]Initiating Smart AI Benchmark across {len(policies)} policies on {sample_size} tasks...[/bold cyan]"
    )

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description="Running benchmark suite on gateway...", total=None)
            bench_res = client.run_benchmark(policies=policies, sample_size=sample_size)

        if json_output:
            console.print_json(json.dumps(bench_res.model_dump()))
            return

        # 1. Comparative Results Table
        table = Table(
            title=f"Benchmark Comparison Results ({bench_res.cases_evaluated} Tasks Evaluated)",
            header_style="bold cyan",
            border_style="dim",
        )
        table.add_column("Policy", style="bold white")
        table.add_column("Pass Rate", justify="right")
        table.add_column("Avg Score", justify="right")
        table.add_column("Total Cost (USD)", justify="right", style="bold cyan")
        table.add_column("Avg Cost/Task", justify="right")
        table.add_column("Avg Latency", justify="right")
        table.add_column("Fallbacks", justify="center")

        for pol_name in policies:
            s = bench_res.summaries.get(pol_name)
            if not s:
                continue
            pass_color = "green" if s.pass_rate_pct >= 90 else "yellow"
            table.add_row(
                s.policy,
                f"[{pass_color}]{s.pass_rate_pct:.1f}%[/]",
                f"{s.avg_score:.2f}",
                f"${s.total_cost:.6f}",
                f"${s.avg_cost_per_task:.6f}",
                f"{s.avg_latency_ms:.1f}ms",
                str(s.fallback_count),
            )

        console.print(table)

        # 2. Highlight Adaptive Savings
        savings = bench_res.adaptive_savings_vs_strong_pct
        savings_color = "bold green" if savings > 0 else "yellow"
        print_status_card(
            "Benchmark Cost Efficiency",
            {
                "Dataset Version": bench_res.dataset_version,
                "Tasks Evaluated": bench_res.cases_evaluated,
                "Adaptive Savings vs Always Strong": f"[{savings_color}]{savings:.1f}% Cost Reduction[/]",
            },
            border_style="green",
        )

        # 3. Export if requested
        if export:
            if str(export).endswith(".json"):
                export.write_text(json.dumps(bench_res.model_dump(), indent=2), encoding="utf-8")
                print_success(f"Benchmark results exported to JSON: {export}")
            else:
                # Markdown export
                md_content = "# Smart AI Gateway Benchmark Results\n\n"
                md_content += f"- **Dataset Version**: {bench_res.dataset_version}\n"
                md_content += f"- **Cases Evaluated**: {bench_res.cases_evaluated}\n"
                md_content += f"- **Adaptive Savings**: {savings:.1f}%\n\n"
                md_content += "| Policy | Pass Rate | Total Cost | Avg Latency |\n|---|---|---|---|\n"
                for pol_name in policies:
                    s = bench_res.summaries.get(pol_name)
                    if s:
                        md_content += f"| {s.policy} | {s.pass_rate_pct:.1f}% | ${s.total_cost:.6f} | {s.avg_latency_ms:.1f}ms |\n"
                export.write_text(md_content, encoding="utf-8")
                print_success(f"Benchmark results exported to Markdown: {export}")

    except GatewayClientError as exc:
        print_error(f"Benchmark run failed: {exc}")
        raise typer.Exit(code=1)
