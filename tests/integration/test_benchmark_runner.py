"""Integration tests for the benchmark runner across 3 policies."""

import pytest
from app.evaluation.dataset import BenchmarkDataset, EvaluationCase
from app.evaluation.report import generate_markdown_report
from app.evaluation.runner import BenchmarkRunner
from app.repositories.sqlite import SqliteTraceRepository
from app.services.orchestrator import ChatOrchestrator


@pytest.mark.asyncio
async def test_benchmark_runner_three_policies(test_repo: SqliteTraceRepository):
    # Create mini test dataset
    cases = [
        EvaluationCase(
            id="test_c1",
            category="direct",
            prompt="What is HTTP 200?",
            required_tools=[],
            forbidden_tools=["calculator"],
            expected_answer="OK",
            expected_facts=["OK"],
            max_steps=1,
            weights={"answer": 0.5, "tool_selection": 0.3, "trajectory": 0.2},
        ),
        EvaluationCase(
            id="test_c2",
            category="calculation",
            prompt="calculate 50 + 50",
            required_tools=["calculator"],
            forbidden_tools=["lookup"],
            expected_answer=100,
            expected_facts=["100"],
            max_steps=2,
            weights={"answer": 0.5, "tool_selection": 0.3, "trajectory": 0.2},
        ),
    ]
    dataset = BenchmarkDataset(version="test_v1", created_at="2026-11-14", cases=cases)

    orch = ChatOrchestrator(repository=test_repo)
    runner = BenchmarkRunner(orchestrator=orch, dataset=dataset)

    results = await runner.run_all_policies()
    assert len(results.policy_summaries) == 3
    assert "always_cheap" in results.policy_summaries
    assert "always_strong" in results.policy_summaries
    assert "adaptive" in results.policy_summaries

    for pol, summary in results.policy_summaries.items():
        assert summary.total_cases == 2
        assert summary.passed_cases >= 1
        assert summary.avg_score > 0.0

    # Test report generation
    report_md = generate_markdown_report(results)
    assert "# Benchmark Evaluation Report" in report_md
    assert "always_cheap" in report_md
    assert "always_strong" in report_md
    assert "adaptive" in report_md
