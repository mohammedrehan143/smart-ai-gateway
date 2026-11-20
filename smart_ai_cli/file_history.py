"""File Versioning, Snapshot, and History Management for Smart AI Filesystem Engine."""

from __future__ import annotations

import difflib
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class FileHistoryManager:
    """Manages file modification history, snapshots, and rollbacks within a workspace."""

    def __init__(self, workspace_root: Optional[Path | str] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self.history_dir = self.workspace_root / ".smartai" / "history"
        self._manifest_file = self.history_dir / "manifest.json"
        self._ensure_history_dir()

    def _ensure_history_dir(self) -> None:
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def _load_manifest(self) -> Dict[str, List[Dict[str, Any]]]:
        if not self._manifest_file.exists():
            return {}
        try:
            return json.loads(self._manifest_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_manifest(self, manifest: Dict[str, List[Dict[str, Any]]]) -> None:
        self._ensure_history_dir()
        self._manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _rel_path(self, target: Path | str) -> str:
        resolved = (self.workspace_root / target).resolve()
        try:
            return str(resolved.relative_to(self.workspace_root)).replace("\\", "/")
        except ValueError:
            return str(resolved).replace("\\", "/")

    def snapshot(self, file_path: Path | str, description: str = "snapshot") -> Optional[str]:
        """Creates a snapshot of the current file before an edit/write/delete. Returns snapshot id."""
        resolved = (self.workspace_root / file_path).resolve()
        if not resolved.exists() or not resolved.is_file():
            return None

        try:
            content = resolved.read_bytes()
            sha = hashlib.sha256(content).hexdigest()[:12]
            ts = int(time.time() * 1000)
            rel = self._rel_path(resolved)
            snapshot_id = f"{ts}_{sha}"
            snap_file = self.history_dir / f"{snapshot_id}.bin"
            snap_file.write_bytes(content)

            manifest = self._load_manifest()
            history = manifest.setdefault(rel, [])
            history.append(
                {
                    "id": snapshot_id,
                    "timestamp": ts,
                    "sha256": sha,
                    "size": len(content),
                    "description": description,
                }
            )
            self._save_manifest(manifest)
            return snapshot_id
        except Exception:
            return None

    def get_history(self, file_path: Path | str) -> List[Dict[str, Any]]:
        """Retrieves snapshot history for a file."""
        rel = self._rel_path(file_path)
        manifest = self._load_manifest()
        return manifest.get(rel, [])

    def get_diff(self, file_path: Path | str, snapshot_id: Optional[str] = None) -> Tuple[bool, str]:
        """Generates unified diff between current file and a snapshot (or latest snapshot)."""
        resolved = (self.workspace_root / file_path).resolve()
        rel = self._rel_path(resolved)
        manifest = self._load_manifest()
        history = manifest.get(rel, [])
        if not history:
            return False, f"No snapshot history recorded for '{rel}'."

        target_snap = None
        if snapshot_id:
            for s in history:
                if s["id"] == snapshot_id:
                    target_snap = s
                    break
            if not target_snap:
                return False, f"Snapshot '{snapshot_id}' not found for '{rel}'."
        else:
            target_snap = history[-1]

        snap_file = self.history_dir / f"{target_snap['id']}.bin"
        if not snap_file.exists():
            return False, f"Snapshot file for ID '{target_snap['id']}' is missing on disk."

        try:
            old_lines = snap_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            new_lines = (
                resolved.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                if resolved.exists()
                else []
            )

            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"{rel} ({target_snap['id']})",
                tofile=f"{rel} (current)",
            )
            diff_text = "".join(diff)
            return True, diff_text if diff_text.strip() else "(No differences found)"
        except Exception as exc:
            return False, f"Diff generation error: {exc}"

    def rollback(self, file_path: Path | str, snapshot_id: Optional[str] = None) -> Tuple[bool, str]:
        """Restores file to previous snapshot version and takes a snapshot of the current state."""
        resolved = (self.workspace_root / file_path).resolve()
        rel = self._rel_path(resolved)
        manifest = self._load_manifest()
        history = manifest.get(rel, [])
        if not history:
            return False, f"No snapshot history recorded for '{rel}' to roll back to."

        target_snap = None
        if snapshot_id:
            for s in history:
                if s["id"] == snapshot_id:
                    target_snap = s
                    break
            if not target_snap:
                return False, f"Snapshot '{snapshot_id}' not found for '{rel}'."
        else:
            target_snap = history[-1]

        snap_file = self.history_dir / f"{target_snap['id']}.bin"
        if not snap_file.exists():
            return False, f"Snapshot file for ID '{target_snap['id']}' is missing on disk."

        try:
            # Snapshot current state before rollback
            if resolved.exists():
                self.snapshot(resolved, description="pre-rollback backup")

            resolved.parent.mkdir(parents=True, exist_ok=True)
            content = snap_file.read_bytes()
            resolved.write_bytes(content)

            if not resolved.exists() or resolved.stat().st_size != len(content):
                return False, f"Verification failed: rolled back file '{rel}' is corrupted on disk."

            return True, f"Successfully rolled back '{rel}' to version {target_snap['id']} ({len(content)} bytes)."
        except Exception as exc:
            return False, f"Rollback failed for '{rel}': {exc}"


default_file_history_manager = FileHistoryManager()
