"""Unit tests for Smart AI Autonomous Planning and DAG Execution Engine."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from smart_ai_cli.dag_executor import DAGExecutor
from smart_ai_cli.planner import ExecutionPlan, SubTask, TaskPlanner, TaskStatus


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_execution_plan_dependencies_and_checkpointing(temp_workspace):
    plan = ExecutionPlan(
        task_id="test_plan_001",
        goal="Build feature",
        workspace_root=str(temp_workspace),
    )

    t1 = SubTask(id="step_1", title="Step 1", description="Init", tool_name="list_directory", tool_args={"path": "."})
    t2 = SubTask(
        id="step_2",
        title="Step 2",
        description="Generate",
        tool_name="write_file",
        tool_args={"path": "a.txt", "content": "A"},
        dependencies=["step_1"],
    )
    plan.subtasks = [t1, t2]

    # Only step_1 is ready initially
    ready = plan.get_executable_subtasks()
    assert len(ready) == 1
    assert ready[0].id == "step_1"

    # Save checkpoint
    chk_file = plan.save_checkpoint()
    assert chk_file.exists()

    # Load checkpoint
    loaded = ExecutionPlan.load_checkpoint(chk_file)
    assert loaded is not None
    assert loaded.task_id == "test_plan_001"
    assert len(loaded.subtasks) == 2


def test_task_planner_decomposition(temp_workspace):
    planner = TaskPlanner(temp_workspace)

    web_plan = planner.decompose("create a website in this folder")
    assert len(web_plan.subtasks) >= 3
    assert any("index.html" in t.tool_args.get("path", "") for t in web_plan.subtasks)

    backend_plan = planner.decompose("build a backend api in python")
    assert len(backend_plan.subtasks) >= 3
    assert any("app.py" in t.tool_args.get("path", "") for t in backend_plan.subtasks)


def test_dag_executor_successful_run(temp_workspace):
    executor = DAGExecutor(temp_workspace)

    plan = ExecutionPlan(
        task_id="run_001",
        goal="Scaffold files",
        workspace_root=str(temp_workspace),
    )
    t1 = SubTask(
        id="s1",
        title="Create file 1",
        description="",
        tool_name="write_file",
        tool_args={"path": "file1.txt", "content": "Content 1"},
    )
    t2 = SubTask(
        id="s2",
        title="Create file 2",
        description="",
        tool_name="write_file",
        tool_args={"path": "file2.txt", "content": "Content 2"},
        dependencies=["s1"],
    )
    plan.subtasks = [t1, t2]

    executed = executor.execute_plan(plan)
    assert executed.is_complete is True
    assert (temp_workspace / "file1.txt").exists()
    assert (temp_workspace / "file2.txt").exists()
    assert executed.status == TaskStatus.COMPLETED

    report = executed.generate_report()
    assert "2/2 steps completed successfully" in report


def test_dag_executor_interrupted_checkpoint_recovery(temp_workspace):
    executor = DAGExecutor(temp_workspace)

    # 1. Simulate a plan where step 1 completed, but step 2 was interrupted
    plan = ExecutionPlan(
        task_id="resume_plan_001",
        goal="Resume test",
        workspace_root=str(temp_workspace),
    )
    t1 = SubTask(
        id="step_a",
        title="Step A",
        description="",
        tool_name="write_file",
        tool_args={"path": "alpha.txt", "content": "Alpha Done"},
        status=TaskStatus.COMPLETED,
    )
    t2 = SubTask(
        id="step_b",
        title="Step B",
        description="",
        tool_name="write_file",
        tool_args={"path": "beta.txt", "content": "Beta Done"},
        dependencies=["step_a"],
        status=TaskStatus.PENDING,
    )
    plan.subtasks = [t1, t2]

    checkpoint_file = plan.save_checkpoint()
    assert checkpoint_file.exists()

    # 2. Resume execution from checkpoint
    resumed_plan = executor.resume_from_checkpoint(checkpoint_file)
    assert resumed_plan is not None
    assert resumed_plan.is_complete is True
    assert (temp_workspace / "beta.txt").exists()
