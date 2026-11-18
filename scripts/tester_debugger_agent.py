#!/usr/bin/env python3
"""
Tester Debugger & Deployment Agent
===================================
Automated quality gate, diagnostic debugger, and deployment pusher for Smart AI Gateway.

Responsibilities:
1. Lint and code hygiene audit via Ruff (with auto-healing).
2. Complete test suite execution via Pytest.
3. Render deployment blueprint validation.
4. Master Orchestrator phase status verification.
5. Automated Git staging, committing, and upstream pushing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = WORKSPACE_ROOT / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = WORKSPACE_ROOT / ".venv" / "bin" / "python"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)


class TesterDebuggerAgent:
    """Autonomous agent that tests, debugs, verifies deployment, and pushes to git."""

    def __init__(self, root: Path = WORKSPACE_ROOT):
        self.root = root
        self.python_bin = str(VENV_PYTHON)
        self.report: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "lint_passed": False,
            "tests_passed": False,
            "render_valid": False,
            "orchestrator_passed": False,
            "git_pushed": False,
        }

    def log(self, section: str, msg: str) -> None:
        print(f"[{section}] {msg}")

    def run_cmd(self, cmd: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
        work_dir = str(cwd or self.root)
        res = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)
        return res.returncode, res.stdout, res.stderr

    def step_lint_and_debug(self) -> bool:
        self.log("LINTER/DEBUGGER", "Running code hygiene and lint inspection...")
        code, stdout, stderr = self.run_cmd([self.python_bin, "-m", "ruff", "check", "app/", "tests/"])
        if code == 0:
            self.log("LINTER/DEBUGGER", "100% clean - no lint or formatting errors found.")
            self.report["lint_passed"] = True
            return True

        self.log("LINTER/DEBUGGER", "Issues detected. Running automated debugger repair (--fix)...")
        fix_code, fix_out, _ = self.run_cmd([self.python_bin, "-m", "ruff", "check", "app/", "tests/", "--fix"])
        if fix_code == 0:
            self.log("LINTER/DEBUGGER", "Automated repair succeeded. Re-verifying...")
            self.report["lint_passed"] = True
            return True
        else:
            self.log("LINTER/DEBUGGER", f"Repair incomplete. Remaining issues:\n{fix_out}")
            return False

    def step_run_test_suite(self) -> bool:
        self.log("TESTER", "Running complete test suite with Pytest...")
        code, stdout, stderr = self.run_cmd([self.python_bin, "-m", "pytest", "-v", "--tb=short"])
        print(stdout)
        if code != 0 and stderr:
            print(stderr)

        if code == 0:
            self.log("TESTER", "All unit and integration tests passed successfully!")
            self.report["tests_passed"] = True
            return True
        else:
            self.log("TESTER", f"Test failures encountered (exit code {code}).")
            return False

    def step_validate_render_spec(self) -> bool:
        self.log("RENDER_VALIDATOR", "Validating Render deployment blueprint...")
        render_yaml = self.root / "render.yaml"
        if not render_yaml.exists():
            self.log("RENDER_VALIDATOR", "FAIL: render.yaml does not exist.")
            return False

        content = render_yaml.read_text(encoding="utf-8")
        required_keys = ["services:", "type: web", "buildCommand:", "startCommand:", "healthCheckPath:"]
        missing = [k for k in required_keys if k not in content]
        if missing:
            self.log("RENDER_VALIDATOR", f"FAIL: render.yaml missing required keys: {missing}")
            return False

        req_txt = self.root / "requirements.txt"
        if not req_txt.exists():
            self.log("RENDER_VALIDATOR", "FAIL: requirements.txt is missing.")
            return False

        self.log("RENDER_VALIDATOR", "render.yaml and requirements.txt are valid for Render deployment.")
        self.report["render_valid"] = True
        return True

    def step_verify_orchestrator(self) -> bool:
        self.log("ORCHESTRATOR", "Checking Master Orchestrator status across all 6 phases...")
        code, stdout, _ = self.run_cmd([self.python_bin, "scripts/master_orchestrator.py", "status"])
        print(stdout)
        if code == 0 and "VERIFIED" in stdout:
            self.report["orchestrator_passed"] = True
            return True
        return False

    def step_git_deploy(
        self, commit_msg: str = "feat: Render deployable release with complete test suite and orchestrator"
    ) -> bool:
        self.log("DEPLOYER", "Initiating Git deployment step...")

        # 1. Check git remote
        code, remotes, _ = self.run_cmd(["git", "remote", "-v"])
        if code != 0 or not remotes.strip():
            self.log("DEPLOYER", "FAIL: No git remote configured.")
            return False
        self.log("DEPLOYER", f"Target remote:\n{remotes.strip()}")

        # 2. Stage all files
        self.log("DEPLOYER", "Staging all project files (git add .)...")
        code, _, stderr = self.run_cmd(["git", "add", "."])
        if code != 0:
            self.log("DEPLOYER", f"FAIL: git add failed: {stderr}")
            return False

        # 3. Check if anything to commit
        code, status_out, _ = self.run_cmd(["git", "status", "--porcelain"])
        if status_out.strip():
            self.log("DEPLOYER", f"Creating commit with message: '{commit_msg}'...")
            code, commit_out, stderr = self.run_cmd(["git", "commit", "-m", commit_msg])
            if code != 0:
                self.log("DEPLOYER", f"FAIL: git commit failed: {stderr}")
                return False
            self.log("DEPLOYER", commit_out.splitlines()[0] if commit_out else "Committed.")
        else:
            self.log("DEPLOYER", "Working directory clean; nothing new to commit.")

        # 4. Push to remote origin main
        self.log("DEPLOYER", "Pushing branch to upstream git repository (git push origin main)...")
        code, push_out, push_err = self.run_cmd(["git", "push", "origin", "main"])
        if code == 0:
            self.log("DEPLOYER", "SUCCESS: Repository successfully pushed to GitHub!")
            self.report["git_pushed"] = True
            return True
        else:
            # Check if upstream needs pull or set-upstream
            self.log("DEPLOYER", f"Push output: {push_out}\nError: {push_err}")
            self.log("DEPLOYER", "Attempting push with tracking: git push -u origin main...")
            code2, push_out2, push_err2 = self.run_cmd(["git", "push", "-u", "origin", "main"])
            if code2 == 0:
                self.log("DEPLOYER", "SUCCESS: Branch pushed and tracking set on origin/main!")
                self.report["git_pushed"] = True
                return True
            else:
                self.log("DEPLOYER", f"Push failed: {push_err2}")
                return False

    def execute_all(self, push: bool = True) -> bool:
        print("\n" + "=" * 80)
        print(" TESTER DEBUGGER & DEPLOYMENT AGENT - PIPELINE EXECUTION")
        print("=" * 80 + "\n")

        # 1. Lint & Debug
        if not self.step_lint_and_debug():
            self.log("PIPELINE", "HALTING: Linting and hygiene checks failed.")
            return False

        # 2. Render Blueprint Validation
        if not self.step_validate_render_spec():
            self.log("PIPELINE", "HALTING: Render deployment spec validation failed.")
            return False

        # 3. Test Suite
        if not self.step_run_test_suite():
            self.log("PIPELINE", "HALTING: Pytest test suite failed.")
            return False

        # 4. Master Orchestrator Verification
        if not self.step_verify_orchestrator():
            self.log("PIPELINE", "HALTING: Master Orchestrator verification failed.")
            return False

        # 5. Git Deployment Step
        if push:
            if not self.step_git_deploy():
                self.log("PIPELINE", "HALTING: Git push step failed.")
                return False

        print("\n" + "=" * 80)
        print(" TESTER DEBUGGER AGENT: ALL GATES PASSED & CODE DEPLOYED SUCCESSFULLY!")
        print("=" * 80 + "\n")
        return True


def main():
    parser = argparse.ArgumentParser(description="Tester Debugger & Deployment Agent")
    parser.add_argument("--no-push", action="store_true", help="Run tests and validation without pushing to git")
    parser.add_argument(
        "-m",
        "--message",
        default="feat: Render deployable release with complete test suite and orchestrator",
        help="Commit message",
    )
    args = parser.parse_args()

    agent = TesterDebuggerAgent()
    success = agent.execute_all(push=not args.no_push)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
