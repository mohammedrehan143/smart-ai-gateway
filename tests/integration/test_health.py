"""Integration tests for health endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_live(async_client: AsyncClient):
    resp = await async_client.get("/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "live"
    assert "timestamp" in data
    assert data["gateway_version"] == "0.1.0"


@pytest.mark.asyncio
async def test_health_ready(async_client: AsyncClient):
    resp = await async_client.get("/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
