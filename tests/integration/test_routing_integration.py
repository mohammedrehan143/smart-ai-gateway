"""Integration tests for deterministic auto-routing through POST /v1/chat."""

import pytest
from httpx import AsyncClient
from app.repositories.sqlite import SqliteTraceRepository


@pytest.mark.asyncio
async def test_adaptive_routing_routes_code_to_strong(
    async_client: AsyncClient, test_repo: SqliteTraceRepository
):
    payload = {
        "messages": [
            {
                "role": "user",
                "content": "Can you review this python implementation?\n```python\ndef factorial(n):\n    return 1 if n <= 1 else n * factorial(n - 1)\n```",
            }
        ],
        "routing": {"policy": "adaptive"},
    }

    resp = await async_client.post("/v1/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["routing"]["policy"] == "adaptive"
    assert data["routing"]["tier"] == "strong"
    assert "code" in data["routing"]["reason"].lower() or "debugging" in data["routing"]["reason"].lower()
    assert data["model"] == "mock-strong"

    # Verify routing decision persisted in SQLite
    req_id = data["id"]
    async with test_repo._get_conn() as conn:
        cursor = await conn.execute(
            "SELECT * FROM routing_decisions WHERE gateway_request_id = ?",
            (req_id,),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["tier"] == "strong"
        assert row["reason_code"] == "CODE_OR_DEBUGGING_DETECTED"
