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
    prompt: Optional[str] = None,
    classification_level: Optional[int] = None,
    reason: Optional[str] = None,
    agent: Optional[str] = None,
    provider: Optional[str] = None,
    mock_mode: Optional[bool] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
) -> None:
    """Prints comprehensive execution provenance, routing classification, and cost metrics."""
    cost_str = f"${cost:.6f}" if cost is not None else "N/A"
    cache_badge = " [bold blue]⚡cached[/]" if cached else ""
    trace_str = f"[dim]tr:{trace_id[:16]}[/]" if trace_id else ""

    # Agent badge
    agent_name = agent or ("Weak Agent" if tier == "cheap" else "Strong Agent")
    agent_color = "green" if "weak" in agent_name.lower() or tier == "cheap" else "magenta"
    agent_badge = f"[bold {agent_color}]{agent_name}[/]"

    # Level badge
    level_num = classification_level if classification_level is not None else (1 if tier == "cheap" else 3)
    level_label = "Simple" if level_num == 1 else ("Moderate" if level_num == 2 else "Complex")
    level_str = f"[bold cyan]Level {level_num}[/] [dim]({level_label})[/]"

    # Mock mode indicator
    is_mock = mock_mode if mock_mode is not None else (provider == "mock" or "mock" in model.lower())
    mock_indicator = "[bold red]Enabled (Simulated)[/]" if is_mock else "[bold green]Disabled (Real API)[/]"

    # Tokens detail
    in_tok = input_tokens or 0
    out_tok = output_tokens or 0
    tok_str = (
        f"[white]{tokens}[/] [dim](in: {in_tok}, out: {out_tok})[/]" if (in_tok or out_tok) else f"[white]{tokens}[/]"
    )

    lines = []
    if prompt:
        truncated_prompt = prompt if len(prompt) <= 70 else prompt[:67] + "..."
        lines.append(f"[dim]Prompt:[/] [bold italic]{truncated_prompt}[/]")

    lines.append(f"[dim]Classification:[/] {level_str} • [dim]Reason:[/] {reason or 'Standard routing heuristic'}")
    lines.append(
        f"[dim]Routing:[/] {agent_badge} [dim]({tier})[/] • [dim]Provider:[/] [yellow]{provider or 'openai'}[/] • [dim]Model:[/] [bold white]{model}[/]"
    )
    lines.append(
        f"[dim]Mock Mode:[/] {mock_indicator} • [dim]Latency:[/] [cyan]{latency_ms}ms[/] • [dim]Tokens:[/] {tok_str} • [dim]Cost:[/] [bold cyan]{cost_str}[/]"
    )
    if trace_str or cache_badge:
        lines.append(f"{trace_str}{cache_badge}".strip())

    summary_text = "\n".join(lines)
    panel = Panel(summary_text, border_style="dim", expand=False)
    if indent > 0:
        console.print(Padding(panel, (0, 0, 0, indent)))
    else:
        console.print(panel)
