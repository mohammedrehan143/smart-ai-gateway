"""Rich Terminal User Interface components and formatters for Smart AI CLI."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from rich.align import Align
from rich.box import ROUNDED
from rich.console import Console
from rich.padding import Padding
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

console = Console()
error_console = Console(stderr=True)


class ChatPrompt(Prompt):
    """Custom prompt with clean suffix for interactive chatting."""
    prompt_suffix = " "

ASCII_BANNER = r"""[bold cyan]
   ____                      __     ___    ____   ________    ____
  / __/___ ___  ____ _____  / /_   /   |  /  _/  / ____/ /   /  _/
 _\ \ / __ `__ \/ __ `/ __ \/ __/  / /| |  / /   / /   / /    / /
/___// / / / / / /_/ / /_/ / /_   / ___ |_/ /   / /___/ /____/ /
     /_/ /_/ /_/\__,_/\__,_/\__/  /_/  |_/___/   \____/_____/___/
[/bold cyan][dim]Modular AI Gateway Developer CLI • Intelligent Auto-Routing & LLMOps[/dim]
"""


def print_banner(include_subtitle: bool = True) -> None:
    """Displays distinctive professional ASCII branding."""
    console.print(ASCII_BANNER)
    if include_subtitle:
        console.print()


def print_success(message: str) -> None:
    console.print(f"[bold green]✔[/bold green] {message}")


def print_warning(message: str) -> None:
    console.print(f"[bold yellow]▲[/bold yellow] {message}")


def print_error(message: str, hint: Optional[str] = None) -> None:
    error_console.print(f"[bold red]✖[/bold red] [red]{message}[/red]")
    if hint:
        error_console.print(f"  [dim cyan]Hint:[/] {hint}")


def render_tier_badge(tier: str) -> Text:
    t = tier.lower()
    if t == "cheap":
        return Text("cheap", style="bold green")
    elif t == "strong":
        return Text("strong", style="bold magenta")
    return Text(tier, style="bold yellow")


def render_cost_badge(cost: Optional[float], currency: str = "USD", status: str = "calculated") -> Text:
    if cost is None:
        return Text("N/A", style="dim")
    formatted = f"${cost:.6f}" if cost < 0.01 else f"${cost:.4f}"
    if status == "calculated":
        return Text(formatted, style="bold cyan")
    elif status == "estimated":
        return Text(f"{formatted} (est)", style="yellow")
    return Text(f"{formatted} (?)", style="dim")


def print_status_card(title: str, items: Dict[str, Any], border_style: str = "cyan") -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold white")
    table.add_column(style="dim")

    for k, v in items.items():
        table.add_row(f"{k}:", str(v))

    panel = Panel(
        table,
        title=f"[bold {border_style}]{title}[/]",
        border_style=border_style,
        expand=False,
    )
    console.print(panel)


def print_table(
    title: str,
    columns: List[str],
    rows: List[List[Any]],
    header_style: str = "bold cyan",
) -> None:
    """Renders a structured, clean terminal table."""
    table = Table(title=title, header_style=header_style, border_style="dim")
    for col in columns:
        table.add_column(col)

    for row in rows:
        table.add_row(*[str(cell) if not isinstance(cell, Text) else cell for cell in row])

    console.print(table)


def print_chat_header(gateway_url: str, policy: str, temperature: float) -> None:
    """Displays a modern, centered header for interactive chat sessions."""
    header_text = Text.from_markup(
        f"[bold cyan]Smart AI Gateway[/bold cyan] [dim]• Interactive Chat[/dim]\n"
        f"[dim]Connected:[/] [white]{gateway_url}[/]  •  [dim]Policy:[/] [yellow]{policy}[/]  •  [dim]Temp:[/] [white]{temperature}[/]\n"
        f"[dim]Commands: /help • /reset • /policy • /exit[/dim]",
        justify="center",
    )
    console.print()
    console.print(Align.center(Panel(header_text, border_style="dim", box=ROUNDED, padding=(0, 2), expand=False)))
    console.print()


def print_chat_metadata(
    model: str,
    tier: str,
    policy: str,
    latency_ms: int,
    tokens: int,
    cost: Optional[float],
    cached: bool = False,
    trace_id: Optional[str] = None,
    indent: int = 0,
) -> None:
    """Prints a concise execution summary pill under chat responses."""
    badge_tier = f"[{'green' if tier == 'cheap' else 'magenta'}]{tier}[/]"
    cost_str = f"${cost:.6f}" if cost is not None else "N/A"
    cache_badge = " [bold blue]⚡cached[/]" if cached else ""
    trace_str = f" • [dim]tr:{trace_id[:16]}[/]" if trace_id else ""

    summary_text = (
        f"[dim]model:[/] [bold white]{model}[/] ({badge_tier}) • "
        f"[dim]policy:[/] [yellow]{policy}[/] • "
        f"[dim]latency:[/] [cyan]{latency_ms}ms[/] • "
        f"[dim]tokens:[/] [white]{tokens}[/] • "
        f"[dim]cost:[/] [bold cyan]{cost_str}[/]"
        f"{cache_badge}{trace_str}"
    )
    panel = Panel(summary_text, border_style="dim", expand=False)
    if indent > 0:
        console.print(Padding(panel, (0, 0, 0, indent)))
    else:
        console.print(panel)
