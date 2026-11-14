"""Benchmark and evaluation API endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, status
from app.api.deps import get_orchestrator, verify_gateway_auth
from app.evaluation.dataset import load_benchmark_dataset
from app.evaluation.runner import BenchmarkRunner
from app.services.orchestrator import ChatOrchestrator

router = APIRouter(prefix="/v1/benchmark", tags=["Benchmark"])


class BenchmarkRunRequest(BaseModel):
    policies: List[str] = Field(default=["adaptive", "always_cheap", "always_strong"])
    sample_size: Optional[int] = Field(default=None, ge=1, le=50, description="Optional slice limit for quick runs")


@router.post(
    "/run",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
async def run_benchmark(
    request: BenchmarkRunRequest = BenchmarkRunRequest(),
    orchestrator: ChatOrchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Executes evaluation dataset tasks against requested policies and computes comparative metrics."""
    full_dataset = load_benchmark_dataset()
    if request.sample_size and request.sample_size < len(full_dataset.cases):
        dataset_to_run = type(full_dataset)(
            version=full_dataset.version,
            description=full_dataset.description,
            cases=full_dataset.cases[: request.sample_size],
        )
    else:
        dataset_to_run = full_dataset

    runner = BenchmarkRunner(orchestrator=orchestrator, dataset=dataset_to_run)
    summaries: Dict[str, Any] = {}

    for policy in request.policies:
        summary = await runner.run_policy(policy)
        summaries[policy] = {
            "policy": summary.policy_name,
            "total_cases": summary.total_cases,
            "passed_cases": summary.passed_cases,
            "pass_rate_pct": summary.pass_rate_pct,
            "avg_score": round(summary.avg_score, 4),
            "total_cost": round(summary.total_cost, 6),
            "avg_cost_per_task": round(summary.avg_cost_per_task, 6),
            "avg_latency_ms": round(summary.avg_latency_ms, 2),
            "fallback_count": summary.fallback_count,
            "category_scores": {k: round(v, 4) for k, v in summary.category_scores.items()},
        }

    # Calculate savings vs always_strong
    strong_cost = summaries.get("always_strong", {}).get("total_cost", 0.0)
    adaptive_cost = summaries.get("adaptive", {}).get("total_cost", 0.0)
    savings_pct = round(((strong_cost - adaptive_cost) / strong_cost) * 100, 2) if strong_cost > 0 else 0.0

    return {
        "dataset_version": dataset_to_run.version,
        "cases_evaluated": len(dataset_to_run.cases),
        "summaries": summaries,
        "adaptive_savings_vs_strong_pct": savings_pct,
    }


@router.get(
    "/latest",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
async def get_latest_benchmark_report() -> Dict[str, Any]:
    """Returns the latest persisted benchmark report summary."""
    report_path = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "BENCHMARK_REPORT.md"
    if report_path.exists():
        content = report_path.read_text(encoding="utf-8")
        return {"found": True, "content": content}
    return {"found": False, "content": "No benchmark report found."}
