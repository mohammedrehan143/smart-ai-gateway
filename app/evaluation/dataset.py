"""Dataset loader for versioned benchmark evaluation tasks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

DATASET_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "evaluation_dataset" / "benchmark_tasks_v1.json"


@dataclass
class EvaluationCase:
    id: str
    category: str
    prompt: str
    required_tools: List[str]
    forbidden_tools: List[str]
    expected_answer: Union[str, int, float]
    expected_facts: List[str]
    max_steps: int
    weights: Dict[str, float]


@dataclass
class BenchmarkDataset:
    version: str
    created_at: str
    cases: List[EvaluationCase]


def load_benchmark_dataset(file_path: Optional[Path] = None) -> BenchmarkDataset:
    """Load and validate the benchmark tasks dataset from JSON."""
    path = file_path or DATASET_DEFAULT_PATH
    if not path.exists():
        raise FileNotFoundError(f"Benchmark dataset file not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = [
        EvaluationCase(
            id=t["id"],
            category=t["category"],
            prompt=t["prompt"],
            required_tools=t.get("required_tools", []),
            forbidden_tools=t.get("forbidden_tools", []),
            expected_answer=t["expected_answer"],
            expected_facts=t.get("expected_facts", []),
            max_steps=t.get("max_steps", 2),
            weights=t.get("weights", {"answer": 0.5, "tool_selection": 0.3, "trajectory": 0.2}),
        )
        for t in data.get("tasks", [])
    ]

    return BenchmarkDataset(
        version=data.get("version", "1.0.0"),
        created_at=data.get("created_at", ""),
        cases=cases,
    )
