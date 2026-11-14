"""Integration tests for provider telemetry and cost provenance."""

import pytest
from httpx import AsyncClient
from app.repositories.sqlite import SqliteTraceRepository


@pytest.mark.asyncio
async def test_provider_telemetry_and_cost_provenance(
    async_client: AsyncClient, test_repo: SqliteTraceRepository
):
    payload = {
        "messages": [
            {"role": "user", "content": "Tell me a short joke about latency."},
        ],
        "routing": {
            "policy": "always_cheap",
        },
    }

    resp = await async_client.post("/v1/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    # Check HTTP response envelope
    usage = data["usage"]
    assert usage["total_tokens"] > 0
    assert usage["cost_status"] == "calculated"
    assert usage["cost_estimate"] is not None
    assert usage["cost_estimate"] > 0.0

    # Verify queryable trace record in SQLite
    req_id = data["id"]
    db_usage = await test_repo.get_usage(req_id)
    assert db_usage is not None
    assert db_usage.cost_status == "calculated"
    assert db_usage.rate_card_id is not None
    assert db_usage.input_rate is not None
    assert db_usage.output_rate is not None
    assert db_usage.estimated_cost == usage["cost_estimate"]
