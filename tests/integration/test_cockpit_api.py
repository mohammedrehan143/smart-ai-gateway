"""Integration tests for Engineering Cockpit API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_cockpit_status_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/cockpit/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "online"
        assert "metrics" in data
        assert "git" in data


@pytest.mark.asyncio
async def test_cockpit_terminal_execution():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Safe command
        resp = await client.post(
            "/api/cockpit/terminal",
            json={"command": "python -c \"print('COCKPIT_TERMINAL_OK')\""},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["exit_code"] == 0
        assert "COCKPIT_TERMINAL_OK" in data["output"]

        # Dangerous command blocked
        bad_resp = await client.post(
            "/api/cockpit/terminal",
            json={"command": "rm -rf /"},
        )
        assert bad_resp.status_code == 400
        err_data = bad_resp.json()
        assert "blocked" in err_data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_cockpit_files_and_plan():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Files listing
        resp = await client.get("/api/cockpit/files")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # Planning DAG
        plan_resp = await client.post(
            "/api/cockpit/plan",
            json={"goal": "create a responsive landing page"},
        )
        assert plan_resp.status_code == 200
        pdata = plan_resp.json()
        assert pdata["success"] is True
        assert len(pdata["plan"]["subtasks"]) >= 3


@pytest.mark.asyncio
async def test_cockpit_agents_and_git():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Agents roster
        resp = await client.get("/api/cockpit/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) >= 8

        # Git info
        git_resp = await client.get("/api/cockpit/git")
        assert git_resp.status_code == 200
        gdata = git_resp.json()
        assert "is_git_repo" in gdata
