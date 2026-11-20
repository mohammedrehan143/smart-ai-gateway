"""Engineering Cockpit Endpoints for Smart AI Gateway Web Workspace."""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import AuthenticatedUser, get_authenticated_user
from smart_ai_cli.codebase_intel import default_codebase_intel
from smart_ai_cli.database_manager import default_database_manager
from smart_ai_cli.filesystem import default_workspace_fs
from smart_ai_cli.git_engine import default_git_engine
from smart_ai_cli.multi_agent import default_orchestrator
from smart_ai_cli.planner import default_task_planner
from smart_ai_cli.process_manager import default_process_manager
from smart_ai_cli.project_memory import default_project_memory
from smart_ai_cli.security_engine import default_security_engine

router = APIRouter(prefix="/api/cockpit", tags=["Engineering Cockpit"])


class TerminalRunRequest(BaseModel):
    command: str = Field(..., min_length=1, description="Command to execute")
    timeout_seconds: int = Field(60, ge=1, le=300)


class PlanRequest(BaseModel):
    goal: str = Field(..., min_length=1, description="Goal to decompose into execution DAG")


class DatabaseQueryRequest(BaseModel):
    sql: str = Field(..., min_length=1, description="SQL query string")
    db_path: str = Field("app.db", description="Database file path")
    allow_destructive: bool = Field(False, description="Authorize destructive queries")


@router.get("/status")
async def get_cockpit_status(user: AuthenticatedUser = Depends(get_authenticated_user)) -> Dict[str, Any]:
    """Returns aggregated status of the engineering workspace."""
    git_ok, git_status = default_git_engine.get_status()
    metrics = default_codebase_intel.scan_project_metrics()
    bg_procs = default_process_manager.list_background_processes()
    memory_ctx = default_project_memory.get_memory_context()

    return {
        "status": "online",
        "workspace_root": str(default_workspace_fs.workspace_root),
        "git": git_status if git_ok else {"error": "Not a git repo"},
        "metrics": metrics,
        "background_processes": bg_procs,
        "memory_summary": memory_ctx,
    }


@router.post("/terminal")
async def run_terminal_command(
    payload: TerminalRunRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> Dict[str, Any]:
    """Executes a terminal command with security guardrails."""
    is_safe, reason, is_high_risk = default_security_engine.validate_command(payload.command)
    if not is_safe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"type": "security_block", "message": reason}},
        )

    success, output, code = default_process_manager.run_command(
        command=payload.command,
        timeout_seconds=payload.timeout_seconds,
    )

    scrubbed_out = default_security_engine.scrub_secrets(output)
    return {
        "success": success,
        "exit_code": code,
        "output": scrubbed_out,
        "is_high_risk": is_high_risk,
    }


@router.get("/files")
async def list_workspace_files(
    path: Optional[str] = Query(None),
    recursive: bool = Query(False),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> Dict[str, Any]:
    """Lists files in the workspace directory."""
    ok, listing = default_workspace_fs.list_directory(path=path, recursive=recursive)
    return {"success": ok, "listing": listing}


@router.get("/file")
async def read_workspace_file(
    path: str = Query(..., description="Path to file"),
    start_line: Optional[int] = Query(None),
    end_line: Optional[int] = Query(None),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> Dict[str, Any]:
    """Reads file content from workspace."""
    ok, content = default_workspace_fs.read_file(path=path, start_line=start_line, end_line=end_line)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=content)
    return {"success": True, "path": path, "content": content}


@router.post("/plan")
async def generate_execution_plan(
    payload: PlanRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> Dict[str, Any]:
    """Decomposes user goal into a structured DAG ExecutionPlan."""
    plan = default_task_planner.decompose(payload.goal)
    return {"success": True, "plan": plan.to_dict()}


@router.get("/agents")
async def list_agents(user: AuthenticatedUser = Depends(get_authenticated_user)) -> Dict[str, Any]:
    """Lists specialized agents and blackboard file locks."""
    roster = [
        {
            "name": ag.name,
            "role": ag.role.value,
            "description": ag.system_prompt,
        }
        for ag in default_orchestrator.agents.values()
    ]
    return {
        "agents": roster,
        "file_locks": default_orchestrator.blackboard.file_locks,
        "recent_messages": [
            {
                "sender": m.sender,
                "recipient": m.recipient,
                "content": m.content,
                "timestamp": m.timestamp,
            }
            for m in default_orchestrator.blackboard.messages[-10:]
        ],
    }


@router.get("/git")
async def get_git_info(user: AuthenticatedUser = Depends(get_authenticated_user)) -> Dict[str, Any]:
    """Retrieves git repository status, diff, and recent commits."""
    git_ok, status_info = default_git_engine.get_status()
    diff_ok, diff_text = default_git_engine.get_diff()
    log_ok, logs = default_git_engine.get_log(max_count=10)

    return {
        "is_git_repo": git_ok,
        "status": status_info if git_ok else {},
        "diff": diff_text if diff_ok else "",
        "recent_commits": logs if log_ok else [],
    }


@router.post("/query")
async def execute_database_query(
    payload: DatabaseQueryRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> Dict[str, Any]:
    """Executes SQL query against database."""
    ok, result = default_database_manager.execute_query(
        sql=payload.sql,
        db_path=payload.db_path,
        allow_destructive=payload.allow_destructive,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(result))
    return {"success": True, "result": result}


@router.get("/schema")
async def inspect_database_schema(
    db_path: str = Query("app.db"),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> Dict[str, Any]:
    """Inspects database schema."""
    ok, schema = default_database_manager.inspect_schema(db_path=db_path)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=schema)
    return {"success": True, "schema": schema}
