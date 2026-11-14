"""End-to-End Pipeline test validating complete gateway lifecycle."""

import pytest
from httpx import AsyncClient
from app.repositories.sqlite import SqliteTraceRepository


@pytest.mark.asyncio
async def test_full_gateway_e2e_lifecycle(
    async_client: AsyncClient, test_repo: SqliteTraceRepository
):
    # 1. Health checks
    live_resp = await async_client.get("/health/live")
    assert live_resp.status_code == 200
    assert live_resp.json()["status"] == "live"

    ready_resp = await async_client.get("/health/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json()["status"] == "ready"

    # 2. Public Chat Generation with Code Prompt (Adaptive Routing -> Strong tier)
    chat_payload = {
        "messages": [
            {"role": "system", "content": "You are a code reviewer."},
            {"role": "user", "content": "Review this implementation:\n```python\ndef compute(x): return x * 2\n```"},
        ],
        "routing": {"policy": "adaptive"},
        "parameters": {"temperature": 0.0, "max_output_tokens": 256},
    }

    resp1 = await async_client.post("/v1/chat", json=chat_payload, headers={"X-Request-ID": "e2e-req-1"})
    assert resp1.status_code == 200
    data1 = resp1.json()

    # Invariants
    assert data1["object"] == "gateway.completion"
    assert data1["routing"]["tier"] == "strong"
    assert data1["routing"]["fallback_used"] is False
    assert data1["usage"]["cost_status"] == "calculated"
    assert data1["cached"] is False

    # 3. Cache verification (Identical temperature 0.0 request)
    resp2 = await async_client.post("/v1/chat", json=chat_payload, headers={"X-Request-ID": "e2e-req-2"})
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cached"] is True
    assert data2["routing"]["reason"] == "Served from cache"

    # 4. Durable SQLite Trace Inspection
    trace_id = data1["trace_id"]
    db_req = await test_repo.get_request_by_trace_id(trace_id)
    assert db_req is not None
    assert db_req.status == "success"
    assert db_req.routing_policy == "adaptive"

    attempts = await test_repo.get_attempts(db_req.id)
    assert len(attempts) >= 1
    assert attempts[0].status == "success"

    usage = await test_repo.get_usage(db_req.id)
    assert usage is not None
    assert usage.cost_status == "calculated"
    assert usage.estimated_cost is not None
