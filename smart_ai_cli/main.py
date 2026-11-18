"""Main CLI Entrypoint for Smart AI CLI."""

from __future__ import annotations

from typing import Optional
import typer

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from smart_ai_cli import __app_name__, __version__
from smart_ai_cli.commands.benchmark import benchmark_cmd
from smart_ai_cli.commands.chat import ask_cmd, chat_cmd
from smart_ai_cli.commands.config import app as config_app
from smart_ai_cli.commands.cost import cost_cmd
from smart_ai_cli.commands.login import login_cmd, logout_cmd
from smart_ai_cli.commands.models import models_cmd
from smart_ai_cli.commands.route import route_cmd
from smart_ai_cli.commands.status import status_cmd
from smart_ai_cli.commands.task import do_cmd, task_cmd
from smart_ai_cli.commands.usage import usage_cmd
from smart_ai_cli.ui import console

app = typer.Typer(
    name=__app_name__,
    help="Smart AI CLI - Production Developer Command-Line Interface for Smart AI Gateway.",
    no_args_is_help=True,
    add_completion=False,
)


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold cyan]{__app_name__}[/] version [bold green]{__version__}[/]")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show Smart AI CLI version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Smart AI CLI: Developer Command-Line Interface for Smart AI Gateway."""
    pass


# Register individual top-level commands
app.command(name="login")(login_cmd)
app.command(name="logout")(logout_cmd)
app.command(name="status")(status_cmd)
app.command(name="chat")(chat_cmd)
app.command(name="ask")(ask_cmd)
app.command(name="models")(models_cmd)
app.command(name="usage")(usage_cmd)
app.command(name="cost")(cost_cmd)
app.command(name="route")(route_cmd)
app.command(name="benchmark")(benchmark_cmd)
app.command(name="do")(do_cmd)
app.command(name="task")(task_cmd)
app.add_typer(config_app, name="config")


if __name__ == "__main__":
    app()
