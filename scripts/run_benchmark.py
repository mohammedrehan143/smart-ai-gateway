"""CLI benchmark runner generating empirical benchmark reports."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.dataset import load_benchmark_dataset
from app.evaluation.report import generate_markdown_report
from app.evaluation.runner import BenchmarkRunner
from app.repositories.sqlite import SqliteTraceRepository
from app.services.orchestrator import ChatOrchestrator

REPORT_FILE = ROOT / "docs" / "BENCHMARK_REPORT.md"


async def main():
    print(">>> Executing Full Empirical Benchmark Evaluation across 3 Policies...")
    repo = SqliteTraceRepository("sqlite:///./benchmark_telemetry.db")
    await repo.initialize()

    orch = ChatOrchestrator(repository=repo)
    dataset = load_benchmark_dataset()
    print(f"Loaded {len(dataset.cases)} benchmark tasks (Dataset v{dataset.version})")

    runner = BenchmarkRunner(orchestrator=orch, dataset=dataset)
    results = await runner.run_all_policies()

    report_md = generate_markdown_report(results)
    REPORT_FILE.write_text(report_md, encoding="utf-8")
    print(f"\nSuccessfully generated benchmark report at: {REPORT_FILE}\n")
    print(report_md)


if __name__ == "__main__":
    asyncio.run(main())
