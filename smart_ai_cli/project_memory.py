"""Persistent Project Memory and Context Knowledge Base for Smart AI Gateway.

Maintains long-term memory across sessions:
- Architecture profile and tech stack conventions.
- Chronological modification history.
- Knowledge base of past errors and verified resolutions.
- User-specified instructions and constraints.
- Compact memory context injection for LLM prompts.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProjectMemoryManager:
    """Stores and retrieves persistent project memory across CLI sessions."""

    def __init__(self, workspace_root: Optional[Path | str] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self.memory_dir = self.workspace_root / ".smartai"
        self.memory_file = self.memory_dir / "project_memory.json"
        self._ensure_storage()
        self._memory = self._load()

    def _ensure_storage(self) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Any]:
        if not self.memory_file.exists():
            return {
                "project_name": self.workspace_root.name,
                "created_at": time.time(),
                "updated_at": time.time(),
                "conventions": {},
                "modifications": [],
                "error_resolutions": [],
                "user_instructions": [],
            }
        try:
            return json.loads(self.memory_file.read_text(encoding="utf-8"))
        except Exception:
            return {
                "project_name": self.workspace_root.name,
                "created_at": time.time(),
                "updated_at": time.time(),
                "conventions": {},
                "modifications": [],
                "error_resolutions": [],
                "user_instructions": [],
            }

    def save(self) -> None:
        """Persists memory to disk."""
        self._memory["updated_at"] = time.time()
        self.memory_file.write_text(json.dumps(self._memory, indent=2), encoding="utf-8")

    def record_modification(self, file_path: str, summary: str, author: str = "agent") -> None:
        """Records a file change to memory."""
        mods = self._memory.setdefault("modifications", [])
        mods.append(
            {
                "timestamp": time.time(),
                "file": file_path,
                "summary": summary,
                "author": author,
            }
        )
        # Keep last 100 modifications
        if len(mods) > 100:
            self._memory["modifications"] = mods[-100:]
        self.save()

    def record_error_resolution(self, error_type: str, root_cause: str, fix_summary: str) -> None:
        """Stores an error and its verified fix in memory."""
        resolutions = self._memory.setdefault("error_resolutions", [])
        resolutions.append(
            {
                "timestamp": time.time(),
                "error_type": error_type,
                "root_cause": root_cause,
                "fix_summary": fix_summary,
            }
        )
        if len(resolutions) > 50:
            self._memory["error_resolutions"] = resolutions[-50:]
        self.save()

    def search_error_solution(self, error_text: str) -> Optional[Dict[str, Any]]:
        """Looks up if this error was previously encountered and resolved."""
        lower_err = error_text.lower()
        for res in reversed(self._memory.get("error_resolutions", [])):
            if res.get("error_type", "").lower() in lower_err or res.get("root_cause", "").lower() in lower_err:
                return res
        return None

    def add_user_instruction(self, instruction: str) -> None:
        """Stores a persistent user preference or rule."""
        instructions = self._memory.setdefault("user_instructions", [])
        if instruction not in instructions:
            instructions.append(instruction)
            self.save()

    def get_user_instructions(self) -> List[str]:
        return self._memory.get("user_instructions", [])

    def get_memory_context(self) -> str:
        """Produces a compact context summary for prompt injection."""
        lines = [
            f"PROJECT CONTEXT: {self._memory.get('project_name', 'Workspace')}",
        ]
        instructions = self.get_user_instructions()
        if instructions:
            lines.append("PERSISTENT USER RULES:")
            for inst in instructions:
                lines.append(f"- {inst}")

        recent_mods = self._memory.get("modifications", [])[-5:]
        if recent_mods:
            lines.append("RECENT WORKSPACE MODIFICATIONS:")
            for m in recent_mods:
                lines.append(f"- {m['file']}: {m['summary']}")

        recent_fixes = self._memory.get("error_resolutions", [])[-3:]
        if recent_fixes:
            lines.append("LEARNED ERROR RESOLUTIONS:")
            for f in recent_fixes:
                lines.append(f"- {f['error_type']}: {f['fix_summary']}")

        return "\n".join(lines)


default_project_memory = ProjectMemoryManager()
