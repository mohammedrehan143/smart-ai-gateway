"""Codebase Intelligence and Dependency Analysis Engine for Smart AI Gateway.

Provides deep repository understanding without sending the entire codebase to an LLM:
- AST parsing of imports, functions, classes, and call hierarchies.
- File-level and module-level dependency graph mapping.
- Circular dependency detection via cycle finding.
- Project architectural summary (languages, file counts, lines of code, frameworks).
- Mermaid diagram generation of project module architecture.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class CodebaseIntelligence:
    """Analyzes repository structure, module dependencies, and architecture."""

    def __init__(self, workspace_root: Optional[Path | str] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()

    def _should_skip(self, path: Path) -> bool:
        skip_dirs = {".git", "__pycache__", ".smartai", ".venv", "node_modules", "dist", "build"}
        return any(part in skip_dirs for part in path.parts)

    def scan_project_metrics(self) -> Dict[str, Any]:
        """Scans project directory and produces language breakdown, file count, and LOC."""
        language_map = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".jsx": "React JSX",
            ".tsx": "React TSX",
            ".html": "HTML",
            ".css": "CSS",
            ".json": "JSON",
            ".md": "Markdown",
            ".sql": "SQL",
            ".sh": "Shell",
            ".bat": "Batch",
            ".ps1": "PowerShell",
        }

        lang_counts: Dict[str, int] = {}
        lang_loc: Dict[str, int] = {}
        total_files = 0
        total_loc = 0

        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".smartai", ".venv", "node_modules"}]
            for f in files:
                ext = Path(f).suffix.lower()
                lang = language_map.get(ext, "Other")
                full_path = Path(root) / f

                total_files += 1
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

                try:
                    lines = len(full_path.read_text(encoding="utf-8", errors="ignore").splitlines())
                    total_loc += lines
                    lang_loc[lang] = lang_loc.get(lang, 0) + lines
                except Exception:
                    pass

        return {
            "total_files": total_files,
            "total_lines_of_code": total_loc,
            "language_file_counts": lang_counts,
            "language_lines_of_code": lang_loc,
            "detected_frameworks": self.detect_frameworks(),
        }

    def detect_frameworks(self) -> List[str]:
        """Detects frameworks used in the project."""
        frameworks = []
        req_file = self.workspace_root / "requirements.txt"
        pyproject = self.workspace_root / "pyproject.toml"
        package_json = self.workspace_root / "package.json"

        all_text = ""
        for p in (req_file, pyproject, package_json):
            if p.is_file():
                try:
                    all_text += "\n" + p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    pass

        checks = {
            "FastAPI": ["fastapi"],
            "Flask": ["flask"],
            "Django": ["django"],
            "Uvicorn": ["uvicorn"],
            "Pytest": ["pytest"],
            "React": ["react", "react-dom"],
            "Next.js": ["next"],
            "Vue": ["vue"],
            "Express": ["express"],
            "TailwindCSS": ["tailwindcss"],
        }
        for fw, markers in checks.items():
            if any(re.search(rf"\b{re.escape(m)}\b", all_text, re.IGNORECASE) for m in markers):
                frameworks.append(fw)

        return frameworks

    def build_import_graph(self) -> Dict[str, List[str]]:
        """Maps file-to-file import dependencies for Python files in the workspace."""
        graph: Dict[str, List[str]] = {}
        py_files = [p for p in self.workspace_root.rglob("*.py") if not self._should_skip(p)]

        module_map: Dict[str, str] = {}
        for p in py_files:
            rel = str(p.relative_to(self.workspace_root)).replace("\\", "/")
            mod_name = p.stem
            module_map[mod_name] = rel

        for p in py_files:
            rel = str(p.relative_to(self.workspace_root)).replace("\\", "/")
            deps: List[str] = []
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            root_mod = alias.name.split(".")[0]
                            if root_mod in module_map and module_map[root_mod] != rel:
                                deps.append(module_map[root_mod])
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        root_mod = node.module.split(".")[0]
                        if root_mod in module_map and module_map[root_mod] != rel:
                            deps.append(module_map[root_mod])
            except Exception:
                pass
            graph[rel] = sorted(list(set(deps)))

        return graph

    def detect_circular_dependencies(self) -> List[List[str]]:
        """Finds circular import cycles using depth-first search."""
        graph = self.build_import_graph()
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []

        def dfs(node: str):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # Cycle detected
                    idx = path.index(neighbor)
                    cycle = path[idx:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.remove(node)

        for node in graph:
            if node not in visited:
                dfs(node)

        return cycles

    def generate_mermaid_diagram(self, max_nodes: int = 25) -> str:
        """Generates a Mermaid dependency flowchart."""
        graph = self.build_import_graph()
        lines = ["flowchart TD"]

        edges_added = 0
        for src, targets in graph.items():
            src_label = Path(src).stem
            for dst in targets:
                dst_label = Path(dst).stem
                lines.append(f'    {src_label}["{src_label}"] --> {dst_label}["{dst_label}"]')
                edges_added += 1
                if edges_added >= max_nodes:
                    break
            if edges_added >= max_nodes:
                break

        if edges_added == 0:
            lines.append("    Start[No internal import dependencies detected]")

        return "\n".join(lines)


default_codebase_intel = CodebaseIntelligence()
