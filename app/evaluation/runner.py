"""Multi-policy benchmark runner executing dataset under always_cheap, always_strong, and adaptive."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from app.evaluation.agent import BenchmarkAgent
from app.evaluation.dataset import BenchmarkDataset, load_benchmark_dataset
from app.evaluation.scorers import CompositeScorer
from app.services.orchestrator import ChatOrchestrator


@dataclass
class CaseEvaluationRecord:
    case_id: str
    category: str
    policy: str
    passed: bool
    total_score: float
    model_alias: str
    latency_ms: int
    tokens: int
    cost: Optional[float]
    fallback_used: bool
    trace_id: str


@dataclass
class PolicySummary:
    policy_name: str
    total_cases: int
    passed_cases: int
    pass_rate_pct: float
    avg_score: float
    total_cost: float
    avg_cost_per_task: float
    avg_latency_ms: float
    fallback_count: int
    category_scores: Dict[str, float] = field(default_factory=dict)


@dataclass
class BenchmarkRunResults:
    dataset_version: str
    policy_summaries: Dict[str, PolicySummary]
    detailed_records: List[CaseEvaluationRecord]


class BenchmarkRunner:
    """Runs evaluation benchmark across the three required policies."""

    def __init__(self, orchestrator: ChatOrchestrator, dataset: Optional[BenchmarkDataset] = None):
        self.orchestrator = orchestrator
        self.dataset = dataset or load_benchmark_dataset()
        self.agent = BenchmarkAgent(orchestrator)

    async def run_policy(self, policy: str) -> PolicySummary:
        records: List[CaseEvaluationRecord] = []
        category_totals: Dict[str, List[float]] = {}

        total_cost = 0.0
        total_latency = 0
        fallback_count = 0
        passed_count = 0
        score_sum = 0.0

        for case in self.dataset.cases:
            exec_res = await self.agent.execute_task(case, policy=policy)
            score_res = CompositeScorer.evaluate(case, exec_res)

            if score_res.passed:
                passed_count += 1
            score_sum += score_res.total_score
            cost_val = exec_res.estimated_cost or 0.0
            total_cost += cost_val
            total_latency += exec_res.latency_ms
            if exec_res.fallback_used:
                fallback_count += 1

            if case.category not in category_totals:
                category_totals[case.category] = []
            category_totals[case.category].append(score_res.total_score)

            records.append(
                CaseEvaluationRecord(
                    case_id=case.id,
                    category=case.category,
                    policy=policy,
                    passed=score_res.passed,
                    total_score=score_res.total_score,
                    model_alias=exec_res.model_alias,
                    latency_ms=exec_res.latency_ms,
                    tokens=exec_res.total_tokens,
                    cost=exec_res.estimated_cost,
                    fallback_used=exec_res.fallback_used,
                    trace_id=exec_res.trace_id,
                )
            )

        n = len(self.dataset.cases)
        cat_scores = {
            cat: round(sum(scores) / len(scores), 3)
            for cat, scores in category_totals.items()
        }

        return PolicySummary(
            policy_name=policy,
            total_cases=n,
            passed_cases=passed_count,
            pass_rate_pct=round((passed_count / n) * 100, 1) if n > 0 else 0.0,
            avg_score=round(score_sum / n, 3) if n > 0 else 0.0,
            total_cost=round(total_cost, 6),
            avg_cost_per_task=round(total_cost / n, 6) if n > 0 else 0.0,
            avg_latency_ms=round(total_latency / n, 1) if n > 0 else 0.0,
            fallback_count=fallback_count,
            category_scores=cat_scores,
        )

    async def run_all_policies(self) -> BenchmarkRunResults:
        policies = ["always_cheap", "always_strong", "adaptive"]
        summaries: Dict[str, PolicySummary] = {}
        for pol in policies:
            summaries[pol] = await self.run_policy(pol)

        return BenchmarkRunResults(
            dataset_version=self.dataset.version,
            policy_summaries=summaries,
            detailed_records=[],
        )
