"""Task execution command: smartai do & smartai task."""

from __future__ import annotations

from typing import Optional
import typer

from smart_ai_cli.agent_runner import AutonomousAgentRunner
from smart_ai_cli.config import default_config_manager

app = typer.Typer(help="Autonomous agent execution for filesystem and terminal tasks.")


@app.command("do")
def do_cmd(
    prompt: str = typer.Argument(..., help="The task for the autonomous agent to perform"),
    policy: Optional[str] = typer.Option(
        None, "--policy", "-p", help="Routing policy (adaptive, always_cheap, always_strong)"
    ),
    temperature: Optional[float] = typer.Option(None, "--temperature", "-t", help="Sampling temperature"),
    max_steps: int = typer.Option(8, "--max-steps", "-s", help="Maximum agent autonomous execution steps"),
    cwd: Optional[str] = typer.Option(None, "--cwd", "-d", help="Working directory for filesystem operations"),
) -> None:
    """Executes an autonomous task: creates files, edits files, inspects code, runs commands."""
    cfg = default_config_manager.load_config()
    active_policy = policy or cfg.default_policy
    active_temp = temperature if temperature is not None else cfg.default_temperature

    runner = AutonomousAgentRunner(max_steps=max_steps)
    res = runner.execute_task(
        task_prompt=prompt,
        policy=active_policy,
        temperature=active_temp,
        cwd=cwd,
    )
    if not res.success:
        raise typer.Exit(code=1)


@app.command("task")
def task_cmd(
    prompt: str = typer.Argument(..., help="The task for the autonomous agent to perform"),
    policy: Optional[str] = typer.Option(
        None, "--policy", "-p", help="Routing policy (adaptive, always_cheap, always_strong)"
    ),
    temperature: Optional[float] = typer.Option(None, "--temperature", "-t", help="Sampling temperature"),
    max_steps: int = typer.Option(8, "--max-steps", "-s", help="Maximum agent autonomous execution steps"),
    cwd: Optional[str] = typer.Option(None, "--cwd", "-d", help="Working directory for filesystem operations"),
) -> None:
    """Alias for 'smartai do': executes an autonomous task directly on the filesystem."""
    do_cmd(prompt=prompt, policy=policy, temperature=temperature, max_steps=max_steps, cwd=cwd)
