"""Autonomous Database Management Engine for Smart AI Gateway.

Provides safe database operations, schema inspection, query execution, and backup:
- SQLite and standard SQL query execution.
- Schema inspection (tables, columns, types, primary keys, foreign keys).
- Migration script generation.
- Guardrails for destructive queries (DROP, TRUNCATE, unconstrained DELETE).
- Atomic database backup and point-in-time restoration.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class DatabaseManager:
    """Manages relational database queries, schema inspection, and backups."""

    def __init__(self, workspace_root: Optional[Path | str] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self.backup_dir = self.workspace_root / ".smartai" / "db_backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_db(self, db_path: Path | str) -> Path:
        p = Path(db_path)
        return p if p.is_absolute() else (self.workspace_root / p).resolve()

    def is_destructive_query(self, sql: str) -> bool:
        """Identifies potentially destructive queries (DROP, TRUNCATE, unconstrained DELETE)."""
        clean = sql.strip().upper()
        if re.search(r"\bDROP\s+(TABLE|DATABASE)\b", clean):
            return True
        if re.search(r"\bTRUNCATE\b", clean):
            return True
        if re.search(r"\bDELETE\s+FROM\b", clean) and "WHERE" not in clean:
            return True
        return False

    def execute_query(
        self,
        sql: str,
        db_path: str = "app.db",
        params: Optional[Tuple[Any, ...]] = None,
        allow_destructive: bool = False,
    ) -> Tuple[bool, Any]:
        """Executes a SQL query against an SQLite database."""
        target_db = self._resolve_db(db_path)
        if self.is_destructive_query(sql) and not allow_destructive:
            return (
                False,
                "Destructive query detected (DROP/TRUNCATE/unconstrained DELETE). Requires explicit authorization.",
            )

        conn = None
        try:
            target_db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(target_db))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            if cursor.description:
                columns = [d[0] for d in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                return True, rows
            else:
                conn.commit()
                return True, {"rows_affected": cursor.rowcount}
        except Exception as exc:
            return False, f"Database execution error: {exc}"
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def inspect_schema(self, db_path: str = "app.db") -> Tuple[bool, Dict[str, Any]]:
        """Extracts schema, tables, columns, and types from database."""
        target_db = self._resolve_db(db_path)
        if not target_db.exists():
            return False, {"error": f"Database file '{db_path}' not found."}

        schema: Dict[str, Any] = {"tables": {}}
        conn = None
        try:
            conn = sqlite3.connect(str(target_db))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [r[0] for r in cursor.fetchall()]

            for tbl in tables:
                cursor.execute(f"PRAGMA table_info('{tbl}');")
                cols = cursor.fetchall()
                schema["tables"][tbl] = [
                    {
                        "cid": c[0],
                        "name": c[1],
                        "type": c[2],
                        "notnull": bool(c[3]),
                        "default_value": c[4],
                        "pk": bool(c[5]),
                    }
                    for c in cols
                ]

            return True, schema
        except Exception as exc:
            return False, {"error": str(exc)}
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def generate_migration(
        self,
        table_name: str,
        columns: Dict[str, str],
        primary_key: str = "id",
    ) -> str:
        """Generates a CREATE TABLE SQL migration snippet."""
        col_defs = []
        for col_name, col_type in columns.items():
            if col_name == primary_key:
                col_defs.append(f"    {col_name} {col_type} PRIMARY KEY")
            else:
                col_defs.append(f"    {col_name} {col_type}")

        sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n" + ",\n".join(col_defs) + "\n);"
        return sql

    def backup(self, db_path: str = "app.db") -> Tuple[bool, str]:
        """Creates a timestamped snapshot backup of the database."""
        src = self._resolve_db(db_path)
        if not src.exists():
            return False, f"Database file '{db_path}' does not exist."

        backup_id = f"backup_{int(time.time() * 1000)}_{src.name}"
        dst = self.backup_dir / backup_id

        try:
            shutil.copy2(str(src), str(dst))
            return True, f"Successfully backed up database to '{dst.name}' ({dst.stat().st_size} bytes)."
        except Exception as exc:
            return False, f"Backup failed: {exc}"

    def restore(self, backup_name: str, db_path: str = "app.db") -> Tuple[bool, str]:
        """Restores database from a snapshot backup."""
        src = self.backup_dir / backup_name
        if not src.exists():
            # Check if full path was provided
            src = Path(backup_name)
        if not src.exists():
            return False, f"Backup file '{backup_name}' not found."

        dst = self._resolve_db(db_path)
        try:
            shutil.copy2(str(src), str(dst))
            return True, f"Successfully restored database '{db_path}' from backup '{src.name}'."
        except Exception as exc:
            return False, f"Restore failed: {exc}"


default_database_manager = DatabaseManager()
