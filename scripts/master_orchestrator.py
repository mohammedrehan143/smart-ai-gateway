#!/usr/bin/env python3
"""
Smart AI Gateway - Master Orchestrator Agent
============================================
Coordinates the multi-phase implementation of Smart AI Gateway according to
PROJECT_CHARTER.md, IMPLEMENTATION_GUIDE.md, and docs/22_IMPLEMENTATION_ROADMAP.md.

Enforces build order, phase gating, automated test verification, and contract invariants.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = WORKSPACE_ROOT / ".orchestrator_state.json"
VENV_PYTHON = WORKSPACE_ROOT / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = WORKSPACE_ROOT / ".venv" / "bin" / "python"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)


@dataclass
class PhaseGate:
    phase_id: int
    name: str
    description: str
    exit_criteria: str
    test_targets: List[str]
    required_files: List[str]
    status: str = "pending"  # pending, in_progress, verified, failed
    last_verified: Optional[str] = None
    tests_passed: int = 0
    tests_failed: int = 0
    evidence: Optional[str] = None
    notes: List[str] = field(default_factory=list)


PHASES: Dict[int, PhaseGate] = {
    1: PhaseGate(
        phase_id=1,
        name="Gateway Foundation",
        description="Core FastAPI service, settings, normalized /v1/chat, mock provider, SQLite trace store, and health endpoints.",
        exit_criteria="Mocked completion travels through POST /v1/chat and produces a queryable trace without credentials.",
        test_targets=[
            "tests/unit/test_config.py",
            "tests/unit/test_schemas.py",
            "tests/unit/test_mock_provider.py",
            "tests/integration/test_health.py",
            "tests/integration/test_chat_api.py",
            "tests/integration/test_trace_persistence.py",
        ],
        required_files=[
            "app/main.py",
            "app/core/config.py",
            "app/core/errors.py",
            "app/core/logging.py",
            "app/domain/entities.py",
            "app/domain/interfaces.py",
            "app/api/schemas.py",
            "app/api/health.py",
            "app/api/v1/chat.py",
            "app/providers/mock.py",
            "app/repositories/sqlite.py",
            "app/services/orchestrator.py",
        ],
    ),
    2: PhaseGate(
        phase_id=2,
        name="Provider Integration & LLMOps",
        description="Hosted OpenAI-compatible provider adapter, model registry, rate cards, usage/cost calculation, and telemetry.",
        exit_criteria="Smoke request produces normalized output and a queryable trace with token and cost provenance.",
        test_targets=[
            "tests/unit/test_cost_calculator.py",
            "tests/unit/test_rate_cards.py",
            "tests/unit/test_openai_adapter.py",
            "tests/integration/test_provider_telemetry.py",
        ],
        required_files=[
            "app/core/rate_cards.py",
            "app/core/cost.py",
            "app/domain/registry.py",
            "app/providers/openai_compatible.py",
        ],
    ),
    3: PhaseGate(
        phase_id=3,
        name="Reliability & Cache",
        description="Timeout deadlines, bounded exponential retry with jitter, fallback model execution, and in-memory TTL response cache.",
        exit_criteria="Tests prove retry, non-retryable handling, fallback execution, and cache hit/miss behavior.",
        test_targets=[
            "tests/unit/test_retry_policy.py",
            "tests/unit/test_cache_service.py",
            "tests/integration/test_retry_fallback.py",
            "tests/integration/test_cache_integration.py",
        ],
        required_files=[
            "app/domain/retry.py",
            "app/domain/cache.py",
            "app/services/cache_service.py",
        ],
    ),
    4: PhaseGate(
        phase_id=4,
        name="Deterministic Auto-Routing",
        description="Feature extraction, configurable thresholds, always-cheap, always-strong, and adaptive routing policies with explainable reasons.",
        exit_criteria="Routing tests pass and every decision can be explained from its recorded features and reason.",
        test_targets=[
            "tests/unit/test_feature_extractor.py",
            "tests/unit/test_router_engine.py",
            "tests/integration/test_routing_integration.py",
        ],
        required_files=[
            "app/domain/features.py",
            "app/domain/router.py",
        ],
    ),
    5: PhaseGate(
        phase_id=5,
        name="Benchmark Agent & Evaluations",
        description="Runtime benchmark agent, deterministic calculator & lookup tools, 30-task dataset, answer/tool/trajectory scorers, and 3-policy runner.",
        exit_criteria="Same task set runs under all 3 policies and produces comparable cost, quality, latency, and reliability metrics.",
        test_targets=[
            "tests/unit/test_benchmark_tools.py",
            "tests/unit/test_scorers.py",
            "tests/integration/test_benchmark_runner.py",
        ],
        required_files=[
            "app/evaluation/agent.py",
            "app/evaluation/tools.py",
            "app/evaluation/dataset.py",
            "app/evaluation/scorers.py",
            "app/evaluation/runner.py",
            "app/evaluation/report.py",
            "evaluation_dataset/benchmark_tasks_v1.json",
        ],
    ),
    6: PhaseGate(
        phase_id=6,
        name="Ship and Demonstrate",
        description="Containerization, Dockerfile, docker-compose, CI workflow, operations runbook, verified benchmark evidence report, and interview demo guide.",
        exit_criteria="Clean setup from documented steps, passing container build & CI checks, and saved empirical benchmark report.",
        test_targets=[
            "tests/integration/test_e2e_pipeline.py",
        ],
        required_files=[
            "Dockerfile",
            "docker-compose.yml",
            ".github/workflows/ci.yml",
            "docs/BENCHMARK_REPORT.md",
        ],
    ),
}


class MasterOrchestratorAgent:
    """Master Orchestrator Agent controlling project construction and quality gates."""

    def __init__(self, workspace_root: Path = WORKSPACE_ROOT):
        self.root = workspace_root
        self.state_file = STATE_FILE
        self.state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        # Initialize default state
        return {
            "project": "Smart AI Gateway",
            "initialized_at": datetime.now(timezone.utc).isoformat(),
            "current_phase": 1,
            "phases": {str(k): asdict(v) for k, v in PHASES.items()},
        }

    def _save_state(self) -> None:
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def print_status(self) -> None:
        print("\n" + "=" * 80)
        print(" SMART AI GATEWAY - MASTER ORCHESTRATOR STATUS")
        print("=" * 80)
        current = self.state.get("current_phase", 1)
        print(f"Active Target Phase: Phase {current} - {PHASES[current].name}\n")
        print(f"{'Phase':<8} {'Name':<32} {'Status':<12} {'Tests (P/F)':<14} {'Last Verified'}")
        print("-" * 80)
        for pid in sorted(PHASES.keys()):
            p_data = self.state["phases"][str(pid)]
            status = p_data.get("status", "pending").upper()
            pf = f"{p_data.get('tests_passed', 0)}/{p_data.get('tests_failed', 0)}"
            verified = p_data.get("last_verified") or "Never"
            if len(verified) > 19:
                verified = verified[:19].replace("T", " ")
            print(f"Phase {pid:<2} {p_data['name']:<32} {status:<12} {pf:<14} {verified}")
        print("=" * 80 + "\n")

    def verify_phase(self, phase_id: int) -> bool:
        if phase_id not in PHASES:
            print(f"[ERROR] Invalid phase {phase_id}. Choose 1-6.")
            return False

        gate = PHASES[phase_id]
        print(f"\n>>> [ORCHESTRATOR] Initiating Verification for Phase {phase_id}: {gate.name}")
        print(f"    Exit Criteria: {gate.exit_criteria}\n")

        # 1. Check required files
        missing_files = []
        for rel_path in gate.required_files:
            file_path = self.root / rel_path
            if not file_path.exists():
                missing_files.append(rel_path)

        if missing_files:
            print(f"[FAIL] Missing required files for Phase {phase_id}:")
            for mf in missing_files:
                print(f"  - {mf}")
            self.state["phases"][str(phase_id)]["status"] = "failed"
            self.state["phases"][str(phase_id)]["notes"] = [f"Missing files: {missing_files}"]
            self._save_state()
            return False

        # 2. Check test targets
        available_tests = []
        for t in gate.test_targets:
            t_path = self.root / t
            if t_path.exists():
                available_tests.append(t)
            else:
                print(f"[WARN] Test target not found yet: {t}")

        if not available_tests:
            print(f"[FAIL] No test targets exist for Phase {phase_id}.")
            self.state["phases"][str(phase_id)]["status"] = "failed"
            self._save_state()
            return False

        # 3. Run pytest on available test targets
        cmd = [str(VENV_PYTHON), "-m", "pytest"] + available_tests + ["-v", "--tb=short"]
        print(f"[EXEC] Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)

        passed = 0
        failed = 0
        for line in result.stdout.splitlines():
            if "passed" in line and ("failed" in line or "error" in line or line.strip().endswith("passed")):
                # summary line like "12 passed in 0.45s"
                pass

        if result.returncode == 0:
            print(f"[PASS] All tests passed for Phase {phase_id}!")
            self.state["phases"][str(phase_id)]["status"] = "verified"
            self.state["phases"][str(phase_id)]["last_verified"] = datetime.now(timezone.utc).isoformat()
            self.state["phases"][str(phase_id)]["evidence"] = f"All {len(available_tests)} test targets passed."
            # Advance current phase if verified
            if self.state["current_phase"] == phase_id and phase_id < 6:
                self.state["current_phase"] = phase_id + 1
            self._save_state()
            return True
        else:
            print(f"[FAIL] Pytest failed with return code {result.returncode}")
            self.state["phases"][str(phase_id)]["status"] = "failed"
            self.state["phases"][str(phase_id)]["last_verified"] = datetime.now(timezone.utc).isoformat()
            self._save_state()
            return False

    def run_all_phases(self) -> bool:
        print("\n>>> [ORCHESTRATOR] Starting Sequential Verification Across All 6 Phases...")
        all_passed = True
        for pid in range(1, 7):
            success = self.verify_phase(pid)
            if not success:
                print(f"\n[BLOCKED] Phase {pid} failed verification. Halting subsequent phases.")
                all_passed = False
                break
        self.print_status()
        return all_passed


def main():
    parser = argparse.ArgumentParser(description="Smart AI Gateway Master Orchestrator")
    parser.add_argument("command", choices=["status", "verify", "run-all"], default="status", nargs="?")
    parser.add_argument("--phase", type=int, choices=range(1, 7), help="Phase number (1-6) to verify")
    args = parser.parse_args()

    orchestrator = MasterOrchestratorAgent()

    if args.command == "status":
        orchestrator.print_status()
    elif args.command == "verify":
        target_phase = args.phase or orchestrator.state.get("current_phase", 1)
        orchestrator.verify_phase(target_phase)
    elif args.command == "run-all":
        orchestrator.run_all_phases()


if __name__ == "__main__":
    main()
