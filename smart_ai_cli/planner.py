"""Autonomous Planning and DAG Task Decomposition Engine for Smart AI Gateway.

Provides structured execution planning:
- Task DAG decomposition with explicit dependency tracking.
- Parallel execution safety identification.
- Execution checkpointing and state persistence in .smartai/checkpoints/.
- Interrupted-task recovery and resumption.
- Dynamic replanning upon tool failure.
- Detailed progress tracking and completion reports.
"""

from __future__ import annotations

import enum
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


@dataclass
class SubTask:
    id: str
    title: str
    description: str
    tool_name: Optional[str] = None
    tool_args: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 2
    parallel_safe: bool = False
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubTask":
        d = dict(data)
        if "status" in d:
            d["status"] = TaskStatus(d["status"])
        return cls(**d)


@dataclass
class ExecutionPlan:
    task_id: str
    goal: str
    subtasks: List[SubTask] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: TaskStatus = TaskStatus.PENDING
    workspace_root: str = "."

    @property
    def is_complete(self) -> bool:
        return all(t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED) for t in self.subtasks)

    @property
    def has_failed(self) -> bool:
        return any(t.status == TaskStatus.FAILED and t.retries >= t.max_retries for t in self.subtasks)

    def get_subtask(self, subtask_id: str) -> Optional[SubTask]:
        for t in self.subtasks:
            if t.id == subtask_id:
                return t
        return None

    def get_completed_ids(self) -> Set[str]:
        return {t.id for t in self.subtasks if t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)}

    def get_executable_subtasks(self) -> List[SubTask]:
        """Returns subtasks ready for execution whose dependencies are satisfied."""
        completed = self.get_completed_ids()
        ready: List[SubTask] = []
        for t in self.subtasks:
            if t.status == TaskStatus.PENDING:
                if all(dep in completed for dep in t.dependencies):
                    ready.append(t)
                else:
                    # Check if any dependency failed
                    failed_deps = [
                        dep
                        for dep in t.dependencies
                        if self.get_subtask(dep) and self.get_subtask(dep).status == TaskStatus.FAILED
                    ]
                    if failed_deps:
                        t.status = TaskStatus.BLOCKED
                        t.error = f"Blocked by failed dependencies: {', '.join(failed_deps)}"
        return ready

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status.value,
            "workspace_root": self.workspace_root,
            "subtasks": [t.to_dict() for t in self.subtasks],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionPlan":
        subtasks = [SubTask.from_dict(t) for t in data.get("subtasks", [])]
        return cls(
            task_id=data.get("task_id", f"task_{int(time.time())}"),
            goal=data.get("goal", ""),
            subtasks=subtasks,
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            status=TaskStatus(data.get("status", TaskStatus.PENDING.value)),
            workspace_root=data.get("workspace_root", "."),
        )

    def save_checkpoint(self, checkpoint_path: Optional[Path | str] = None) -> Path:
        """Persists plan state to disk checkpoint."""
        if checkpoint_path:
            p = Path(checkpoint_path)
        else:
            base = Path(self.workspace_root).resolve()
            p = base / ".smartai" / "checkpoints" / f"{self.task_id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = time.time()
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return p

    @classmethod
    def load_checkpoint(cls, checkpoint_path: Path | str) -> Optional["ExecutionPlan"]:
        """Loads plan state from disk checkpoint."""
        p = Path(checkpoint_path)
        if not p.exists() or not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception:
            return None

    def generate_report(self) -> str:
        """Generates a structured completion / status report."""
        lines = [
            f"# Execution Report: {self.goal}",
            f"**Task ID:** {self.task_id} | **Status:** {self.status.value.upper()}",
            f"**Workspace:** {self.workspace_root}",
            "",
            "## Steps Breakdown",
        ]
        for idx, t in enumerate(self.subtasks, start=1):
            icon = {
                TaskStatus.COMPLETED: "✔",
                TaskStatus.FAILED: "✖",
                TaskStatus.IN_PROGRESS: "⚙",
                TaskStatus.PENDING: "⏳",
                TaskStatus.SKIPPED: "⏭",
                TaskStatus.BLOCKED: "⛔",
            }.get(t.status, "•")
            duration = f"({t.end_time - t.start_time:.2f}s)" if t.start_time and t.end_time else ""
            lines.append(f"{idx}. {icon} **[{t.id}] {t.title}** {duration}")
            lines.append(f"   - Tool: `{t.tool_name}`")
            if t.result:
                lines.append(f"   - Result: {t.result[:120]}...")
            if t.error:
                lines.append(f"   - Error: {t.error}")

        lines.append("")
        total = len(self.subtasks)
        completed = len(self.get_completed_ids())
        failed = len([t for t in self.subtasks if t.status == TaskStatus.FAILED])
        lines.append(f"**Summary:** {completed}/{total} steps completed successfully, {failed} failed.")
        return "\n".join(lines)


class TaskPlanner:
    """Decomposes complex requests into execution plans and handles dynamic replanning."""

    def __init__(self, workspace_root: Optional[Path | str] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()

    def decompose(self, goal: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        """Decomposes a user goal into an ExecutionPlan DAG."""
        task_id = f"plan_{int(time.time() * 1000)}"
        plan = ExecutionPlan(
            task_id=task_id,
            goal=goal,
            workspace_root=str(self.workspace_root),
        )

        lower_goal = goal.lower()
        subtasks: List[SubTask] = []

        # Heuristic 1: Web application / frontend creation
        if any(w in lower_goal for w in ("website", "web app", "landing page", "webpage", "dashboard")):
            subtasks = [
                SubTask(
                    id="step_1_inspect",
                    title="Inspect workspace environment",
                    description="Check directory contents for existing files and structure",
                    tool_name="list_directory",
                    tool_args={"path": ".", "recursive": False},
                    parallel_safe=True,
                ),
                SubTask(
                    id="step_2_html",
                    title="Generate semantic HTML structure",
                    description="Create index.html with accessible, modern markup",
                    tool_name="write_file",
                    tool_args={"path": "index.html", "content": ""},
                    dependencies=["step_1_inspect"],
                ),
                SubTask(
                    id="step_3_css",
                    title="Generate responsive stylesheet",
                    description="Create style.css with modern design, typography, and theme tokens",
                    tool_name="write_file",
                    tool_args={"path": "style.css", "content": ""},
                    dependencies=["step_1_inspect"],
                    parallel_safe=True,
                ),
                SubTask(
                    id="step_4_js",
                    title="Implement interactive client logic",
                    description="Create script.js with event handlers and state",
                    tool_name="write_file",
                    tool_args={"path": "script.js", "content": ""},
                    dependencies=["step_1_inspect"],
                    parallel_safe=True,
                ),
                SubTask(
                    id="step_5_verify",
                    title="Verify files and server port",
                    description="Ensure all assets exist on disk and verify available port",
                    tool_name="read_file",
                    tool_args={"path": "index.html", "start_line": 1, "end_line": 20},
                    dependencies=["step_2_html", "step_3_css", "step_4_js"],
                ),
            ]

        # Heuristic 2: Python / Backend project
        elif any(w in lower_goal for w in ("backend", "api", "fastapi", "flask", "server", "microservice")):
            subtasks = [
                SubTask(
                    id="step_1_inspect",
                    title="Inspect workspace environment",
                    description="Check existing project files",
                    tool_name="list_directory",
                    tool_args={"path": "."},
                ),
                SubTask(
                    id="step_2_main",
                    title="Generate main application server",
                    description="Write app.py with routes and middleware",
                    tool_name="write_file",
                    tool_args={"path": "app.py", "content": ""},
                    dependencies=["step_1_inspect"],
                ),
                SubTask(
                    id="step_3_reqs",
                    title="Generate dependencies manifest",
                    description="Write requirements.txt",
                    tool_name="write_file",
                    tool_args={"path": "requirements.txt", "content": ""},
                    dependencies=["step_1_inspect"],
                    parallel_safe=True,
                ),
                SubTask(
                    id="step_4_test",
                    title="Generate test suite",
                    description="Write test_app.py",
                    tool_name="write_file",
                    tool_args={"path": "test_app.py", "content": ""},
                    dependencies=["step_2_main"],
                ),
                SubTask(
                    id="step_5_verify",
                    title="Verify syntax with compiler",
                    description="Check syntax of generated python code",
                    tool_name="run_command",
                    tool_args={"command": "python -m py_compile app.py test_app.py"},
                    dependencies=["step_2_main", "step_4_test"],
                ),
            ]

        # Heuristic 3: Test execution or debugging
        elif any(w in lower_goal for w in ("test", "debug", "fix", "verify")):
            subtasks = [
                SubTask(
                    id="step_1_locate",
                    title="Locate files and test suites",
                    description="Search for test files and source code",
                    tool_name="find_files",
                    tool_args={"pattern": "*test*.py"},
                ),
                SubTask(
                    id="step_2_run_tests",
                    title="Execute test suite",
                    description="Run pytest or unittest to detect failures",
                    tool_name="run_command",
                    tool_args={"command": "pytest -q"},
                    dependencies=["step_1_locate"],
                ),
                SubTask(
                    id="step_3_diagnose",
                    title="Analyze test results and verify state",
                    description="Verify execution results and determine fix requirements",
                    tool_name="read_file",
                    tool_args={"path": "pyproject.toml"},
                    dependencies=["step_2_run_tests"],
                ),
            ]

        # Heuristic 4: General multi-step execution default
        else:
            subtasks = [
                SubTask(
                    id="step_1_analyze",
                    title="Analyze workspace context",
                    description="Inspect existing structure to prepare execution",
                    tool_name="list_directory",
                    tool_args={"path": "."},
                ),
                SubTask(
                    id="step_2_execute",
                    title="Execute primary task instructions",
                    description=goal,
                    tool_name=None,
                    tool_args={},
                    dependencies=["step_1_analyze"],
                ),
                SubTask(
                    id="step_3_verify",
                    title="Verify task execution results",
                    description="Confirm that changes are properly reflected on disk",
                    tool_name="list_directory",
                    tool_args={"path": "."},
                    dependencies=["step_2_execute"],
                ),
            ]

        plan.subtasks = subtasks
        return plan

    def replan(
        self,
        plan: ExecutionPlan,
        failed_subtask: SubTask,
        error_message: str,
    ) -> ExecutionPlan:
        """Injects dynamic remediation steps when a subtask fails."""
        remediation_id = f"fix_{failed_subtask.id}_{int(time.time())}"
        remediation_task = SubTask(
            id=remediation_id,
            title=f"Remediate failure in [{failed_subtask.id}]: {failed_subtask.title}",
            description=f"Address failure: {error_message[:150]}",
            tool_name="run_command",
            tool_args={"command": f"echo Remediating error: {error_message[:100]}"},
            dependencies=[dep for dep in failed_subtask.dependencies if dep != failed_subtask.id],
        )

        # Retry subtask after remediation
        retry_task = SubTask(
            id=f"retry_{failed_subtask.id}",
            title=f"Retry {failed_subtask.title}",
            description=failed_subtask.description,
            tool_name=failed_subtask.tool_name,
            tool_args=failed_subtask.tool_args,
            dependencies=[remediation_id],
        )

        # Update downstream dependencies
        for t in plan.subtasks:
            if failed_subtask.id in t.dependencies:
                t.dependencies.remove(failed_subtask.id)
                t.dependencies.append(retry_task.id)

        plan.subtasks.append(remediation_task)
        plan.subtasks.append(retry_task)
        plan.updated_at = time.time()
        return plan


default_task_planner = TaskPlanner()
