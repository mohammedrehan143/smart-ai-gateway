"""DAG Task Executor with Checkpointing, Parallel Scheduling, and Dynamic Replanning.

Executes an ExecutionPlan DAG:
- Resolves dependencies dynamically.
- Runs parallel-safe independent tasks concurrently.
- Checkpoints progress to .smartai/checkpoints/ after each step.
- Recovers from interrupted checkpoints.
- Emits real-time progress callbacks.
- Triggers dynamic replanning and retry loops upon step failure.
- Verifies post-execution state.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional, Tuple

from smart_ai_cli.planner import ExecutionPlan, SubTask, TaskPlanner, TaskStatus, default_task_planner
from smart_ai_cli.tools import execute_tool


class DAGExecutor:
    """Executes an ExecutionPlan DAG with checkpointing, concurrency, and replanning."""

    def __init__(
        self,
        workspace_root: Optional[Path | str] = None,
        planner: Optional[TaskPlanner] = None,
        checkpoint_dir: Optional[Path | str] = None,
    ):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self.planner = planner or default_task_planner
        self.checkpoint_dir = (
            Path(checkpoint_dir) if checkpoint_dir else self.workspace_root / ".smartai" / "checkpoints"
        )
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _execute_single_subtask(self, subtask: SubTask) -> Tuple[bool, str]:
        """Executes one subtask using the local tool registry."""
        subtask.status = TaskStatus.IN_PROGRESS
        subtask.start_time = time.time()

        if not subtask.tool_name:
            # Informational / pseudo-step
            subtask.status = TaskStatus.COMPLETED
            subtask.end_time = time.time()
            subtask.result = f"Completed step: {subtask.title}"
            return True, subtask.result

        success, output = execute_tool(
            name=subtask.tool_name,
            args=subtask.tool_args,
            cwd=self.workspace_root,
        )

        subtask.end_time = time.time()
        if success:
            subtask.status = TaskStatus.COMPLETED
            subtask.result = output
            subtask.error = None
        else:
            subtask.status = TaskStatus.FAILED
            subtask.error = output

        return success, output

    def execute_plan(
        self,
        plan: ExecutionPlan,
        max_parallel: int = 4,
        allow_replan: bool = True,
        on_step_update: Optional[Callable[[SubTask, ExecutionPlan], None]] = None,
    ) -> ExecutionPlan:
        """Executes the complete plan DAG to completion or unrecoverable failure."""
        plan.status = TaskStatus.IN_PROGRESS
        plan.workspace_root = str(self.workspace_root)
        plan.save_checkpoint()

        loop_guard = 0
        max_loops = len(plan.subtasks) * 5 + 20

        while not plan.is_complete and not plan.has_failed and loop_guard < max_loops:
            loop_guard += 1
            ready_tasks = plan.get_executable_subtasks()

            if not ready_tasks:
                # Check if everything is done or stuck
                if plan.is_complete:
                    break
                # Blocked or deadlocked
                blocked_tasks = [t for t in plan.subtasks if t.status in (TaskStatus.PENDING, TaskStatus.BLOCKED)]
                if blocked_tasks:
                    plan.status = TaskStatus.FAILED
                    for bt in blocked_tasks:
                        bt.status = TaskStatus.BLOCKED
                        if not bt.error:
                            bt.error = "Unresolvable dependency deadlock or prerequisite failure."
                    break

            # Separate parallel-safe tasks from sequential tasks
            parallel_candidates = [t for t in ready_tasks if t.parallel_safe and len(ready_tasks) > 1]
            if len(parallel_candidates) > 1:
                batch = parallel_candidates[:max_parallel]
                with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                    futures = {executor.submit(self._execute_single_subtask, t): t for t in batch}
                    for f in as_completed(futures):
                        t = futures[f]
                        if on_step_update:
                            on_step_update(t, plan)
            else:
                # Execute first ready subtask sequentially
                task_to_run = ready_tasks[0]
                success, output = self._execute_single_subtask(task_to_run)

                # Retry or Replan on failure
                if not success:
                    task_to_run.retries += 1
                    if task_to_run.retries < task_to_run.max_retries:
                        # Reset for immediate retry
                        task_to_run.status = TaskStatus.PENDING
                    elif allow_replan:
                        # Trigger dynamic replanning
                        plan = self.planner.replan(plan, task_to_run, output)
                        allow_replan = False  # Avoid infinite replan cascades

                if on_step_update:
                    on_step_update(task_to_run, plan)

            plan.save_checkpoint()

        if plan.is_complete:
            plan.status = TaskStatus.COMPLETED
        else:
            plan.status = TaskStatus.FAILED

        plan.save_checkpoint()
        return plan

    def resume_from_checkpoint(
        self,
        checkpoint_path: Path | str,
        on_step_update: Optional[Callable[[SubTask, ExecutionPlan], None]] = None,
    ) -> Optional[ExecutionPlan]:
        """Resumes execution from a persisted checkpoint."""
        plan = ExecutionPlan.load_checkpoint(checkpoint_path)
        if not plan:
            return None
        return self.execute_plan(plan, on_step_update=on_step_update)


default_dag_executor = DAGExecutor()
