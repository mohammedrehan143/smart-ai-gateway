"""Autonomous Filesystem Engine for Smart AI Gateway.

Provides complete filesystem capabilities:
- Create, read, write, edit, delete, rename, move, and copy files.
- Create and delete directories.
- Search files by glob pattern and search file contents (grep).
- Perform bulk/batch file operations.
- Version tracking, snapshotting, diffing, and rollbacks via FileHistoryManager.
- Absolute disk verification for every mutating operation.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from smart_ai_cli.file_history import FileHistoryManager


class WorkspaceFilesystem:
    """Manages filesystem operations within a workspace directory with history tracking."""

    def __init__(self, workspace_root: Optional[Path | str] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self.history = FileHistoryManager(self.workspace_root)

    def _resolve(self, target_path: Path | str, cwd: Optional[Path | str] = None) -> Path:
        base = Path(cwd).resolve() if cwd else self.workspace_root
        p = Path(target_path)
        if p.is_absolute():
            return p.resolve()
        return (base / p).resolve()

    def _rel(self, target: Path) -> str:
        try:
            return str(target.relative_to(self.workspace_root)).replace("\\", "/")
        except ValueError:
            return str(target).replace("\\", "/")

    def write_file(
        self,
        path: str,
        content: str,
        cwd: Optional[Path | str] = None,
        snapshot: bool = True,
    ) -> Tuple[bool, str]:
        """Creates or overwrites a file with content, verifying the write on disk."""
        try:
            resolved = self._resolve(path, cwd)
            # Create snapshot if file exists
            if snapshot and resolved.is_file():
                self.history.snapshot(resolved, description="pre-write snapshot")

            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")

            if not resolved.exists():
                return False, f"Verification failed: file '{path}' not found on disk after write."

            size = resolved.stat().st_size
            return True, f"Successfully created {path} ({size} bytes)"
        except Exception as exc:
            return False, f"Failed to write file '{path}': {exc}"

    def read_file(
        self,
        path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        cwd: Optional[Path | str] = None,
    ) -> Tuple[bool, str]:
        """Reads file contents, optionally slicing by 1-based line numbers."""
        try:
            resolved = self._resolve(path, cwd)
            if not resolved.is_file():
                return False, f"File not found: '{path}'"

            lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            total = len(lines)
            s = max(1, start_line) if start_line is not None else 1
            e = min(total, end_line) if end_line is not None else total

            selected = lines[s - 1 : e]
            numbered = [f"{i + s:4d} | {line}" for i, line in enumerate(selected)]
            output = "".join(numbered)
            return True, output if output else "(file is empty)"
        except Exception as exc:
            return False, f"Failed to read file '{path}': {exc}"

    def edit_file(
        self,
        path: str,
        target: str,
        replacement: str,
        cwd: Optional[Path | str] = None,
        snapshot: bool = True,
    ) -> Tuple[bool, str]:
        """Replaces exact target string with replacement string in file, verifying modification."""
        try:
            resolved = self._resolve(path, cwd)
            if not resolved.is_file():
                return False, f"File not found: '{path}'"

            text = resolved.read_text(encoding="utf-8")
            if target not in text:
                return False, f"Target text not found in '{path}'. Make sure exact characters match."

            if snapshot:
                self.history.snapshot(resolved, description="pre-edit snapshot")

            updated = text.replace(target, replacement, 1)
            resolved.write_text(updated, encoding="utf-8")

            # Verify
            new_text = resolved.read_text(encoding="utf-8")
            if target in new_text and target != replacement:
                return False, f"Verification failed: Target text still found in '{path}' after edit."
            if replacement not in new_text:
                return False, f"Verification failed: Replacement text not found in '{path}' after edit."

            return True, f"Successfully updated '{self._rel(resolved)}'."
        except Exception as exc:
            return False, f"Failed to edit file '{path}': {exc}"

    def delete_file(
        self,
        path: str,
        cwd: Optional[Path | str] = None,
        snapshot: bool = True,
    ) -> Tuple[bool, str]:
        """Deletes a file after taking a history snapshot, and verifies removal."""
        try:
            resolved = self._resolve(path, cwd)
            if not resolved.exists():
                return False, f"File not found: '{path}'"
            if resolved.is_dir():
                return False, f"Path '{path}' is a directory, not a file. Use delete_directory."

            if snapshot:
                self.history.snapshot(resolved, description="pre-deletion snapshot")

            resolved.unlink()
            if resolved.exists():
                return False, f"Verification failed: file '{path}' still exists after deletion attempt."

            return True, f"Successfully deleted '{self._rel(resolved)}'."
        except Exception as exc:
            return False, f"Failed to delete file '{path}': {exc}"

    def rename_file(
        self,
        old_path: str,
        new_path: str,
        cwd: Optional[Path | str] = None,
        snapshot: bool = True,
    ) -> Tuple[bool, str]:
        """Renames a file or directory, verifying the change."""
        try:
            src = self._resolve(old_path, cwd)
            dst = self._resolve(new_path, cwd)

            if not src.exists():
                return False, f"Source path '{old_path}' does not exist."
            if dst.exists():
                return False, f"Destination path '{new_path}' already exists."

            if snapshot and src.is_file():
                self.history.snapshot(src, description=f"rename to {new_path}")

            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)

            if not dst.exists() or src.exists():
                return False, f"Verification failed: rename from '{old_path}' to '{new_path}' failed on disk."

            return True, f"Successfully renamed '{self._rel(src)}' to '{self._rel(dst)}'."
        except Exception as exc:
            return False, f"Failed to rename '{old_path}' to '{new_path}': {exc}"

    def move_file(
        self,
        source: str,
        destination: str,
        cwd: Optional[Path | str] = None,
        snapshot: bool = True,
    ) -> Tuple[bool, str]:
        """Moves a file or directory to a new location."""
        try:
            src = self._resolve(source, cwd)
            dst = self._resolve(destination, cwd)

            if not src.exists():
                return False, f"Source path '{source}' does not exist."

            if dst.is_dir():
                dst = dst / src.name

            if snapshot and src.is_file():
                self.history.snapshot(src, description=f"move to {destination}")

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

            if not dst.exists():
                return False, f"Verification failed: moved target '{destination}' does not exist."

            return True, f"Successfully moved '{self._rel(src)}' to '{self._rel(dst)}'."
        except Exception as exc:
            return False, f"Failed to move '{source}' to '{destination}': {exc}"

    def copy_file(
        self,
        source: str,
        destination: str,
        overwrite: bool = True,
        cwd: Optional[Path | str] = None,
    ) -> Tuple[bool, str]:
        """Copies a file to a new destination and verifies copy integrity."""
        try:
            src = self._resolve(source, cwd)
            dst = self._resolve(destination, cwd)

            if not src.is_file():
                return False, f"Source file '{source}' does not exist or is not a file."

            if dst.is_dir():
                dst = dst / src.name

            if dst.exists() and not overwrite:
                return False, f"Destination file '{destination}' already exists and overwrite=False."

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))

            if not dst.is_file():
                return False, f"Verification failed: copied destination '{destination}' does not exist."

            src_size = src.stat().st_size
            dst_size = dst.stat().st_size
            if src_size != dst_size:
                return False, f"Verification failed: size mismatch (src: {src_size}, dst: {dst_size})."

            return True, f"Successfully copied '{self._rel(src)}' to '{self._rel(dst)}' ({dst_size} bytes)."
        except Exception as exc:
            return False, f"Failed to copy '{source}' to '{destination}': {exc}"

    def create_directory(self, path: str, cwd: Optional[Path | str] = None) -> Tuple[bool, str]:
        """Creates a directory recursively and verifies existence."""
        try:
            resolved = self._resolve(path, cwd)
            resolved.mkdir(parents=True, exist_ok=True)
            if not resolved.is_dir():
                return False, f"Verification failed: directory '{path}' was not created."
            return True, f"Successfully created directory '{self._rel(resolved)}/'."
        except Exception as exc:
            return False, f"Failed to create directory '{path}': {exc}"

    def delete_directory(
        self,
        path: str,
        recursive: bool = True,
        cwd: Optional[Path | str] = None,
    ) -> Tuple[bool, str]:
        """Deletes a directory, with optional recursion, and verifies removal."""
        try:
            resolved = self._resolve(path, cwd)
            if not resolved.exists():
                return False, f"Directory '{path}' does not exist."
            if not resolved.is_dir():
                return False, f"Path '{path}' is a file, not a directory. Use delete_file."

            # Safety check: do not delete workspace root
            if resolved == self.workspace_root:
                return False, "Cannot delete workspace root directory."

            if recursive:
                shutil.rmtree(str(resolved))
            else:
                resolved.rmdir()

            if resolved.exists():
                return False, f"Verification failed: directory '{path}' still exists."

            return True, f"Successfully deleted directory '{self._rel(resolved)}/'."
        except Exception as exc:
            return False, f"Failed to delete directory '{path}': {exc}"

    def list_directory(
        self,
        path: Optional[str] = None,
        recursive: bool = False,
        cwd: Optional[Path | str] = None,
    ) -> Tuple[bool, str]:
        """Lists directory contents."""
        try:
            resolved = self._resolve(path or ".", cwd)
            if not resolved.exists():
                return False, f"Directory not found: '{path}'"
            if not resolved.is_dir():
                return False, f"Path '{path}' is not a directory."

            items = []
            if recursive:
                for p in sorted(resolved.rglob("*")):
                    if any(part in (".git", "__pycache__", ".smartai", ".venv", "node_modules") for part in p.parts):
                        continue
                    rel = self._rel(p)
                    if p.is_dir():
                        items.append(f"[DIR]  {rel}/")
                    else:
                        items.append(f"[FILE] {rel} ({p.stat().st_size} bytes)")
            else:
                for p in sorted(resolved.iterdir()):
                    if p.name in (".git", "__pycache__", ".smartai", ".venv", "node_modules"):
                        continue
                    if p.is_dir():
                        items.append(f"[DIR]  {p.name}/")
                    else:
                        items.append(f"[FILE] {p.name} ({p.stat().st_size} bytes)")

            return True, "\n".join(items) if items else "(directory is empty)"
        except Exception as exc:
            return False, f"Failed to list directory '{path}': {exc}"

    def find_files(
        self,
        pattern: str = "*",
        path: Optional[str] = None,
        cwd: Optional[Path | str] = None,
        max_results: int = 500,
    ) -> Tuple[bool, str]:
        """Finds files matching glob pattern recursively."""
        try:
            resolved = self._resolve(path or ".", cwd)
            if not resolved.is_dir():
                return False, f"Base path '{path}' is not a directory."

            matches: List[str] = []
            for root, dirs, files in os.walk(resolved):
                # Filter out heavy directories in-place
                dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".smartai", ".venv", "node_modules")]
                for filename in files:
                    if fnmatch.fnmatch(filename, pattern):
                        full = Path(root) / filename
                        matches.append(self._rel(full))
                        if len(matches) >= max_results:
                            break
                if len(matches) >= max_results:
                    break

            if not matches:
                return True, f"No files found matching '{pattern}' under '{self._rel(resolved)}'."
            res = f"Found {len(matches)} file(s) matching '{pattern}':\n" + "\n".join(matches)
            return True, res
        except Exception as exc:
            return False, f"Failed to find files: {exc}"

    def search_in_files(
        self,
        query: str,
        path: Optional[str] = None,
        file_pattern: str = "*",
        is_regex: bool = False,
        case_sensitive: bool = False,
        max_results: int = 200,
        cwd: Optional[Path | str] = None,
    ) -> Tuple[bool, str]:
        """Grep search for text or regex inside files."""
        try:
            resolved = self._resolve(path or ".", cwd)
            if not resolved.is_dir():
                return False, f"Base path '{path}' is not a directory."

            flags = 0 if case_sensitive else re.IGNORECASE
            pattern_regex = re.compile(query if is_regex else re.escape(query), flags)

            results: List[str] = []
            count = 0

            for root, dirs, files in os.walk(resolved):
                dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".smartai", ".venv", "node_modules")]
                for filename in files:
                    if not fnmatch.fnmatch(filename, file_pattern):
                        continue
                    full = Path(root) / filename
                    rel = self._rel(full)
                    try:
                        content = full.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        continue

                    for line_idx, line in enumerate(content.splitlines(), start=1):
                        if pattern_regex.search(line):
                            results.append(f"{rel}:{line_idx}: {line.strip()[:140]}")
                            count += 1
                            if count >= max_results:
                                break
                    if count >= max_results:
                        break
                if count >= max_results:
                    break

            if not results:
                return True, f"No matches found for '{query}' in files matching '{file_pattern}'."
            header = f"Found {len(results)} match(es) for '{query}':\n"
            return True, header + "\n".join(results)
        except Exception as exc:
            return False, f"Failed to search in files: {exc}"

    def batch_write_files(
        self,
        files: List[Dict[str, str]],
        cwd: Optional[Path | str] = None,
    ) -> Tuple[bool, str]:
        """Writes multiple files in a single batch, tracking all snapshots."""
        results: List[str] = []
        all_ok = True
        for item in files:
            p = item.get("path", "")
            c = item.get("content", "")
            if not p:
                continue
            ok, msg = self.write_file(p, c, cwd=cwd)
            if not ok:
                all_ok = False
            results.append(f"[{'OK' if ok else 'FAIL'}] {msg}")

        summary = f"Batch write: {len(results)} files processed.\n" + "\n".join(results)
        return all_ok, summary

    def get_file_info(self, path: str, cwd: Optional[Path | str] = None) -> Tuple[bool, Dict[str, Any]]:
        """Retrieves file metadata including size, lines, and timestamps."""
        try:
            resolved = self._resolve(path, cwd)
            if not resolved.exists():
                return False, {"error": f"Path '{path}' does not exist."}

            stat = resolved.stat()
            is_file = resolved.is_file()
            line_count = 0
            if is_file:
                try:
                    line_count = len(resolved.read_text(encoding="utf-8", errors="ignore").splitlines())
                except Exception:
                    line_count = -1

            info = {
                "path": self._rel(resolved),
                "is_file": is_file,
                "is_dir": resolved.is_dir(),
                "size_bytes": stat.st_size,
                "created_time": stat.st_ctime,
                "modified_time": stat.st_mtime,
                "line_count": line_count,
                "suffix": resolved.suffix,
            }
            return True, info
        except Exception as exc:
            return False, {"error": str(exc)}

    def rollback(
        self, path: str, snapshot_id: Optional[str] = None, cwd: Optional[Path | str] = None
    ) -> Tuple[bool, str]:
        """Rolls back a file to its previous or specific snapshot."""
        resolved = self._resolve(path, cwd)
        return self.history.rollback(resolved, snapshot_id)

    def get_diff(
        self, path: str, snapshot_id: Optional[str] = None, cwd: Optional[Path | str] = None
    ) -> Tuple[bool, str]:
        """Shows unified diff between current file and snapshot."""
        resolved = self._resolve(path, cwd)
        return self.history.get_diff(resolved, snapshot_id)

    def get_history(self, path: str, cwd: Optional[Path | str] = None) -> List[Dict[str, Any]]:
        """Retrieves history list for a file."""
        resolved = self._resolve(path, cwd)
        return self.history.get_history(resolved)


default_workspace_fs = WorkspaceFilesystem()
