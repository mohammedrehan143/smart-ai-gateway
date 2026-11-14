"""SQLite implementation of the trace repository."""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, List, Optional
import aiosqlite

from app.domain.entities import (
    GatewayRequestRecord,
    ProviderAttemptRecord,
    RoutingDecision,
    UsageRecord,
    generate_id,
)
from app.repositories.base import BaseTraceRepository


class SqliteTraceRepository(BaseTraceRepository):
    """Asynchronous SQLite persistence for gateway traces."""

    def __init__(self, database_url: str):
        # Format: sqlite:///path/to/db.sqlite or sqlite:///:memory:
        self.db_path = database_url.replace("sqlite:///", "")
        self._shared_conn: Optional[aiosqlite.Connection] = None
        if self.db_path != ":memory:" and not self.db_path.startswith("file:"):
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def _get_conn(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        if self.db_path == ":memory:":
            if self._shared_conn is None:
                self._shared_conn = await aiosqlite.connect(":memory:")
                self._shared_conn.row_factory = aiosqlite.Row
            yield self._shared_conn
        else:
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                yield conn

    async def close(self) -> None:
        if self._shared_conn is not None:
            await self._shared_conn.close()
            self._shared_conn = None

    async def initialize(self) -> None:
        async with self._get_conn() as conn:
            await conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gateway_requests (
                    id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    request_id TEXT,
                    created_at REAL NOT NULL,
                    completed_at REAL,
                    environment TEXT,
                    gateway_version TEXT,
                    api_version TEXT,
                    routing_policy TEXT,
                    routing_policy_version TEXT,
                    status TEXT,
                    error_category TEXT,
                    cache_status TEXT,
                    final_provider TEXT,
                    final_model_alias TEXT,
                    fallback_used INTEGER,
                    latency_ms INTEGER,
                    prompt_fingerprint TEXT,
                    metadata_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_requests_trace ON gateway_requests(trace_id);
                CREATE INDEX IF NOT EXISTS idx_requests_created ON gateway_requests(created_at);

                CREATE TABLE IF NOT EXISTS provider_attempts (
                    id TEXT PRIMARY KEY,
                    gateway_request_id TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    provider TEXT,
                    model_alias TEXT,
                    started_at REAL,
                    completed_at REAL,
                    latency_ms INTEGER,
                    status TEXT,
                    error_category TEXT,
                    http_status INTEGER,
                    retry_after_ms INTEGER,
                    is_fallback INTEGER,
                    provider_request_id TEXT,
                    metadata_json TEXT,
                    FOREIGN KEY(gateway_request_id) REFERENCES gateway_requests(id)
                );
                CREATE INDEX IF NOT EXISTS idx_attempts_req ON provider_attempts(gateway_request_id);

                CREATE TABLE IF NOT EXISTS routing_decisions (
                    id TEXT PRIMARY KEY,
                    gateway_request_id TEXT NOT NULL,
                    policy_name TEXT,
                    policy_version TEXT,
                    selected_provider TEXT,
                    selected_model_alias TEXT,
                    tier TEXT,
                    reason_code TEXT,
                    reason_message TEXT,
                    feature_summary_json TEXT,
                    created_at REAL,
                    FOREIGN KEY(gateway_request_id) REFERENCES gateway_requests(id)
                );
                CREATE INDEX IF NOT EXISTS idx_decisions_req ON routing_decisions(gateway_request_id);

                CREATE TABLE IF NOT EXISTS usage_records (
                    id TEXT PRIMARY KEY,
                    gateway_request_id TEXT NOT NULL,
                    provider_attempt_id TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    total_tokens INTEGER,
                    usage_source TEXT,
                    rate_card_id TEXT,
                    input_rate REAL,
                    output_rate REAL,
                    estimated_cost REAL,
                    currency TEXT,
                    cost_status TEXT,
                    calculated_at REAL,
                    FOREIGN KEY(gateway_request_id) REFERENCES gateway_requests(id)
                );
                CREATE INDEX IF NOT EXISTS idx_usage_req ON usage_records(gateway_request_id);
                """
            )
            await conn.commit()

    async def record_request(self, record: GatewayRequestRecord) -> None:
        async with self._get_conn() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO gateway_requests (
                    id, trace_id, request_id, created_at, completed_at, environment,
                    gateway_version, api_version, routing_policy, routing_policy_version,
                    status, error_category, cache_status, final_provider, final_model_alias,
                    fallback_used, latency_ms, prompt_fingerprint, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.trace_id,
                    record.request_id,
                    record.created_at,
                    record.completed_at,
                    record.environment,
                    record.gateway_version,
                    record.api_version,
                    record.routing_policy,
                    record.routing_policy_version,
                    record.status,
                    record.error_category,
                    record.cache_status,
                    record.final_provider,
                    record.final_model_alias,
                    1 if record.fallback_used else 0,
                    record.latency_ms,
                    record.prompt_fingerprint,
                    json.dumps(record.metadata),
                ),
            )
            await conn.commit()

    async def record_attempt(self, record: ProviderAttemptRecord) -> None:
        async with self._get_conn() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO provider_attempts (
                    id, gateway_request_id, attempt_number, provider, model_alias,
                    started_at, completed_at, latency_ms, status, error_category,
                    http_status, retry_after_ms, is_fallback, provider_request_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.gateway_request_id,
                    record.attempt_number,
                    record.provider,
                    record.model_alias,
                    record.started_at,
                    record.completed_at,
                    record.latency_ms,
                    record.status,
                    record.error_category,
                    record.http_status,
                    record.retry_after_ms,
                    1 if record.is_fallback else 0,
                    record.provider_request_id,
                    json.dumps(record.metadata),
                ),
            )
            await conn.commit()

    async def record_decision(self, record: RoutingDecision, gateway_request_id: str) -> None:
        async with self._get_conn() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO routing_decisions (
                    id, gateway_request_id, policy_name, policy_version, selected_provider,
                    selected_model_alias, tier, reason_code, reason_message,
                    feature_summary_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    generate_id("dec"),
                    gateway_request_id,
                    record.policy_name,
                    record.policy_version,
                    record.selected_provider,
                    record.selected_model_alias,
                    record.tier,
                    record.reason_code,
                    record.reason_message,
                    json.dumps(record.feature_summary),
                    time.time(),
                ),
            )
            await conn.commit()

    async def record_usage(self, record: UsageRecord) -> None:
        async with self._get_conn() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO usage_records (
                    id, gateway_request_id, provider_attempt_id, input_tokens, output_tokens,
                    total_tokens, usage_source, rate_card_id, input_rate, output_rate,
                    estimated_cost, currency, cost_status, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.gateway_request_id,
                    record.provider_attempt_id,
                    record.input_tokens,
                    record.output_tokens,
                    record.total_tokens,
                    record.usage_source,
                    record.rate_card_id,
                    record.input_rate,
                    record.output_rate,
                    record.estimated_cost,
                    record.currency,
                    record.cost_status,
                    time.time(),
                ),
            )
            await conn.commit()

    async def get_request_by_trace_id(self, trace_id: str) -> Optional[GatewayRequestRecord]:
        async with self._get_conn() as conn:
            cursor = await conn.execute(
                "SELECT * FROM gateway_requests WHERE trace_id = ?", (trace_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return GatewayRequestRecord(
                id=row["id"],
                trace_id=row["trace_id"],
                request_id=row["request_id"] or "",
                created_at=row["created_at"],
                completed_at=row["completed_at"],
                environment=row["environment"] or "local",
                gateway_version=row["gateway_version"] or "0.1.0",
                api_version=row["api_version"] or "v1",
                routing_policy=row["routing_policy"] or "adaptive",
                routing_policy_version=row["routing_policy_version"] or "1.0.0",
                status=row["status"] or "success",
                error_category=row["error_category"],
                cache_status=row["cache_status"] or "miss",
                final_provider=row["final_provider"],
                final_model_alias=row["final_model_alias"],
                fallback_used=bool(row["fallback_used"]),
                latency_ms=row["latency_ms"] or 0,
                prompt_fingerprint=row["prompt_fingerprint"] or "",
                metadata=json.loads(row["metadata_json"] or "{}"),
            )

    async def get_attempts(self, gateway_request_id: str) -> List[ProviderAttemptRecord]:
        async with self._get_conn() as conn:
            cursor = await conn.execute(
                "SELECT * FROM provider_attempts WHERE gateway_request_id = ? ORDER BY attempt_number ASC",
                (gateway_request_id,),
            )
            rows = await cursor.fetchall()
            return [
                ProviderAttemptRecord(
                    id=row["id"],
                    gateway_request_id=row["gateway_request_id"],
                    attempt_number=row["attempt_number"],
                    provider=row["provider"] or "",
                    model_alias=row["model_alias"] or "",
                    started_at=row["started_at"] or 0.0,
                    completed_at=row["completed_at"] or 0.0,
                    latency_ms=row["latency_ms"] or 0,
                    status=row["status"] or "success",
                    error_category=row["error_category"],
                    http_status=row["http_status"],
                    retry_after_ms=row["retry_after_ms"],
                    is_fallback=bool(row["is_fallback"]),
                    provider_request_id=row["provider_request_id"],
                    metadata=json.loads(row["metadata_json"] or "{}"),
                )
                for row in rows
            ]

    async def get_usage(self, gateway_request_id: str) -> Optional[UsageRecord]:
        async with self._get_conn() as conn:
            cursor = await conn.execute(
                "SELECT * FROM usage_records WHERE gateway_request_id = ?",
                (gateway_request_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return UsageRecord(
                id=row["id"],
                gateway_request_id=row["gateway_request_id"],
                provider_attempt_id=row["provider_attempt_id"],
                input_tokens=row["input_tokens"] or 0,
                output_tokens=row["output_tokens"] or 0,
                total_tokens=row["total_tokens"] or 0,
                usage_source=row["usage_source"] or "provider",
                rate_card_id=row["rate_card_id"],
                input_rate=row["input_rate"],
                output_rate=row["output_rate"],
                estimated_cost=row["estimated_cost"],
                currency=row["currency"] or "USD",
                cost_status=row["cost_status"] or "unavailable",
            )
