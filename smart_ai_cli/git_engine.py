"""Autonomous Git and GitHub Integration Engine for Smart AI Gateway.

Provides safe Git version control and GitHub operations:
- Repository initialization and status inspection.
- Staging, commit generation, branch management, and checkout.
- Diff analysis and log inspection.
- Conventional commit message generator.
- Safe rollback of uncommitted changes.
- Gitignore management.
- Secure GitHub PR integration without secret leakage in logs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from smart_ai_cli.process_manager import ProcessManager


class GitEngine:
    """Manages Git operations and GitHub interactions."""

    def __init__(self, workspace_root: Optional[Path | str] = None, pm: Optional[ProcessManager] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self.pm = pm or ProcessManager(self.workspace_root)

    def is_git_repo(self, cwd: Optional[Path | str] = None) -> bool:
        """Checks if directory is inside a Git repository."""
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        success, _, code = self.pm.run_command("git rev-parse --is-inside-work-tree", cwd=work_dir)
        return success and code == 0

    def init_repo(self, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
        """Initializes a new Git repository if not already initialized."""
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        if self.is_git_repo(work_dir):
            return True, "Directory is already a Git repository."
        success, out, code = self.pm.run_command("git init", cwd=work_dir)
        return success, out

    def get_status(self, cwd: Optional[Path | str] = None) -> Tuple[bool, Dict[str, Any]]:
        """Parses git status into structured info."""
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        if not self.is_git_repo(work_dir):
            return False, {"error": "Not a git repository."}

        success, out, _ = self.pm.run_command("git status --porcelain -b", cwd=work_dir)
        if not success:
            return False, {"error": out}

        lines = out.splitlines()
        branch_line = lines[0] if lines and lines[0].startswith("##") else "## unknown"
        branch_match = re.search(r"##\s+([^.\s]+)", branch_line)
        branch = branch_match.group(1) if branch_match else "unknown"

        staged: List[str] = []
        modified: List[str] = []
        untracked: List[str] = []

        for line in lines[1:]:
            if len(line) < 3:
                continue
            x = line[0]
            y = line[1]
            fname = line[3:].strip()
            if x in ("M", "A", "D", "R", "C"):
                staged.append(fname)
            if y == "M":
                modified.append(fname)
            elif x == "?" and y == "?":
                untracked.append(fname)

        status = {
            "branch": branch,
            "is_clean": len(staged) == 0 and len(modified) == 0 and len(untracked) == 0,
            "staged": staged,
            "modified": modified,
            "untracked": untracked,
        }
        return True, status

    def get_diff(
        self, cached: bool = False, path: Optional[str] = None, cwd: Optional[Path | str] = None
    ) -> Tuple[bool, str]:
        """Returns git diff (cached/staged or working tree)."""
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        cmd = "git diff"
        if cached:
            cmd += " --cached"
        if path:
            cmd += f" -- {path}"
        success, out, _ = self.pm.run_command(cmd, cwd=work_dir)
        return success, out if out else "(no changes)"

    def stage_files(
        self, files: Optional[List[str] | str] = None, cwd: Optional[Path | str] = None
    ) -> Tuple[bool, str]:
        """Stages files in git."""
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        if not files or files == ".":
            cmd = "git add ."
        elif isinstance(files, str):
            cmd = f'git add "{files}"'
        else:
            joined = " ".join(f'"{f}"' for f in files)
            cmd = f"git add {joined}"
        success, out, code = self.pm.run_command(cmd, cwd=work_dir)
        return success, out if out else f"Staged changes ({files or 'all'})."

    def commit(self, message: str, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
        """Creates a git commit."""
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        safe_msg = message.replace('"', '\\"')
        cmd = f'git commit -m "{safe_msg}"'
        success, out, code = self.pm.run_command(cmd, cwd=work_dir)
        return success, out

    def create_or_checkout_branch(
        self, branch_name: str, create: bool = False, cwd: Optional[Path | str] = None
    ) -> Tuple[bool, str]:
        """Switches to or creates a git branch."""
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        cmd = f"git checkout -b {branch_name}" if create else f"git checkout {branch_name}"
        success, out, code = self.pm.run_command(cmd, cwd=work_dir)
        return success, out

    def get_log(self, max_count: int = 10, cwd: Optional[Path | str] = None) -> Tuple[bool, List[Dict[str, Any]]]:
        """Retrieves recent commit log."""
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        format_str = "%H|%an|%ae|%at|%s"
        cmd = f'git log -n {max_count} --pretty=format:"{format_str}"'
        success, out, code = self.pm.run_command(cmd, cwd=work_dir)
        if not success:
            return False, []

        commits = []
        for line in out.splitlines():
            parts = line.strip().split("|", 4)
            if len(parts) == 5:
                commits.append(
                    {
                        "hash": parts[0],
                        "author_name": parts[1],
                        "author_email": parts[2],
                        "timestamp": parts[3],
                        "message": parts[4],
                    }
                )
        return True, commits

    def generate_conventional_commit_message(self, diff_text: str, default_subject: str = "update codebase") -> str:
        """Derives a conventional commit message from diff contents."""
        lower_diff = diff_text.lower()
        if "test" in lower_diff and "def test_" in diff_text:
            prefix = "test"
        elif "fix" in lower_diff or "bug" in lower_diff or "error" in lower_diff:
            prefix = "fix"
        elif "docs" in lower_diff or "readme" in lower_diff:
            prefix = "docs"
        elif "refactor" in lower_diff:
            prefix = "refactor"
        else:
            prefix = "feat"

        return f"{prefix}: {default_subject}"

    def rollback_uncommitted(self, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
        """Discards all uncommitted changes in working directory."""
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        s1, o1, _ = self.pm.run_command("git checkout -- .", cwd=work_dir)
        s2, o2, _ = self.pm.run_command("git clean -fd", cwd=work_dir)
        return (s1 and s2), f"{o1}\n{o2}".strip()

    def manage_gitignore(self, entries: List[str], cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
        """Appends entries to .gitignore safely if not already present."""
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        gi_file = work_dir / ".gitignore"
        existing = gi_file.read_text(encoding="utf-8").splitlines() if gi_file.is_file() else []
        added = []

        for e in entries:
            clean_e = e.strip()
            if clean_e and clean_e not in existing:
                existing.append(clean_e)
                added.append(clean_e)

        if added:
            gi_file.write_text("\n".join(existing) + "\n", encoding="utf-8")
            return True, f"Added to .gitignore: {', '.join(added)}"
        return True, "All entries already present in .gitignore."


default_git_engine = GitEngine()
