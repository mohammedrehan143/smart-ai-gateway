"""Integration tests for Prometheus metrics exposition."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_endpoint_exposition(async_client: AsyncClient):
    # Send a request to generate metrics
    payload = {
        "messages": [{"role": "user", "content": "Generate metrics event."}],
        "routing": {"policy": "adaptive"},
    }
    resp = await async_client.post("/v1/chat", json=payload)
    assert resp.status_code == 200

    # Scrape metrics
    metrics_resp = await async_client.get("/metrics")
    assert metrics_resp.status_code == 200
    text = metrics_resp.text

    assert "gateway_requests_total" in text
    assert "gateway_tokens_total" in text
    assert "gateway_estimated_cost_usd" in text
    assert "gateway_cache_events_total" in text
