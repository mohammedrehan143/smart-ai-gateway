"""Unit tests for Database Management and DevOps engines."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from smart_ai_cli.database_manager import DatabaseManager
from smart_ai_cli.devops_manager import DevOpsManager


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_database_manager_crud_schema_and_backup(temp_workspace):
    db_mgr = DatabaseManager(temp_workspace)
    db_path = "test.db"

    # 1. Create table
    create_sql = """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE
    );
    """
    ok, res = db_mgr.execute_query(create_sql, db_path=db_path)
    assert ok is True

    # 2. Insert rows
    insert_sql = "INSERT INTO users (name, email) VALUES (?, ?);"
    ok, res = db_mgr.execute_query(insert_sql, db_path=db_path, params=("Alice", "alice@example.com"))
    assert ok is True
    assert res.get("rows_affected") == 1

    # 3. Query rows
    select_sql = "SELECT * FROM users WHERE name = ?;"
    ok, rows = db_mgr.execute_query(select_sql, db_path=db_path, params=("Alice",))
    assert ok is True
    assert len(rows) == 1
    assert rows[0]["email"] == "alice@example.com"

    # 4. Schema inspection
    ok, schema = db_mgr.inspect_schema(db_path=db_path)
    assert ok is True
    assert "users" in schema["tables"]
    col_names = [c["name"] for c in schema["tables"]["users"]]
    assert "name" in col_names
    assert "email" in col_names

    # 5. Destructive query guard
    ok, res = db_mgr.execute_query("DROP TABLE users;", db_path=db_path, allow_destructive=False)
    assert ok is False
    assert "Destructive query detected" in str(res)

    # 6. Backup & Restore
    ok, msg = db_mgr.backup(db_path=db_path)
    assert ok is True

    # Drop with authorization
    ok, res = db_mgr.execute_query("DROP TABLE users;", db_path=db_path, allow_destructive=True)
    assert ok is True

    # Inspect schema after drop
    ok, schema_after = db_mgr.inspect_schema(db_path=db_path)
    assert "users" not in schema_after["tables"]

    # Restore from backup
    backups = list(db_mgr.backup_dir.iterdir())
    assert len(backups) == 1
    ok, msg = db_mgr.restore(backups[0].name, db_path=db_path)
    assert ok is True

    # Verify restored data
    ok, restored_rows = db_mgr.execute_query("SELECT * FROM users;", db_path=db_path)
    assert ok is True
    assert len(restored_rows) == 1


def test_devops_manager_templates(temp_workspace):
    devops = DevOpsManager(temp_workspace)

    # Dockerfile
    py_docker = devops.generate_dockerfile(project_type="python", port=8000)
    assert "FROM python:3.11-slim" in py_docker
    assert "EXPOSE 8000" in py_docker

    node_docker = devops.generate_dockerfile(project_type="node", port=3000)
    assert "FROM node:20-alpine" in node_docker
    assert "EXPOSE 3000" in node_docker

    # Docker compose
    compose = devops.generate_docker_compose()
    assert "version: '3.8'" in compose
    assert "services:" in compose

    # CI workflow
    ci = devops.generate_github_actions_ci()
    assert "name: Smart AI CI" in ci
    assert "pytest -q" in ci
