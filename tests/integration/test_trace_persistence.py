"""Integration tests for trace and attempt persistence in SQLite."""

import pytest
from httpx import AsyncClient
from app.repositories.sqlite import SqliteTraceRepository


@pytest.mark.asyncio
async def test_trace_persisted_to_sqlite(async_client: AsyncClient, test_repo: SqliteTraceRepository):
    payload = {
        "messages": [
            {"role": "user", "content": "Persist my trace please."},
        ],
        "routing": {
            "policy": "always_strong",
        },
    }

    resp = await async_client.post("/v1/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    trace_id = data["trace_id"]
    req_id = data["id"]

    # Verify directly against database
    persisted_req = await test_repo.get_request_by_trace_id(trace_id)
    assert persisted_req is not None
    assert persisted_req.id == req_id
    assert persisted_req.status == "success"
    assert persisted_req.routing_policy == "always_strong"

    # Verify attempt recorded
    attempts = await test_repo.get_attempts(req_id)
    assert len(attempts) == 1
    assert attempts[0].status == "success"
    assert attempts[0].model_alias == "mock-strong"

    # Verify usage record
    usage = await test_repo.get_usage(req_id)
    assert usage is not None
    assert usage.total_tokens > 0
