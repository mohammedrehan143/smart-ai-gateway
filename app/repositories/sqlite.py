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
            if self.db_path != ":memory:":
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA busy_timeout=5000;")
                await conn.execute("PRAGMA synchronous=NORMAL;")
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

                CREATE TABLE IF NOT EXISTS user_credentials (
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    encrypted_key TEXT NOT NULL,
                    base_url TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    PRIMARY KEY(user_id, provider)
                );

                CREATE TABLE IF NOT EXISTS agent_configurations (
                    user_id TEXT NOT NULL,
                    agent_type TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    encrypted_key TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    base_url TEXT,
                    temperature REAL DEFAULT 0.2,
                    max_tokens INTEGER DEFAULT 1024,
                    is_enabled INTEGER DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id, agent_type)
                );

                CREATE TABLE IF NOT EXISTS budget_limits (
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    max_cost_per_request REAL,
                    daily_budget REAL,
                    monthly_budget REAL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(user_id, project_id)
                );

                CREATE TABLE IF NOT EXISTS model_bandit_stats (
                    category TEXT NOT NULL,
                    model_alias TEXT NOT NULL,
                    trials INTEGER DEFAULT 0,
                    successes INTEGER DEFAULT 0,
                    total_reward REAL DEFAULT 0.0,
                    avg_reward REAL DEFAULT 0.5,
                    avg_latency_ms REAL DEFAULT 100.0,
                    avg_cost REAL DEFAULT 0.0005,
                    last_updated REAL NOT NULL,
                    PRIMARY KEY(category, model_alias)
                );

                CREATE TABLE IF NOT EXISTS agentic_execution_steps (
                    id TEXT PRIMARY KEY,
                    gateway_request_id TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    action TEXT NOT NULL,
                    assigned_model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    latency_ms INTEGER,
                    cost REAL,
                    error_message TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(gateway_request_id) REFERENCES gateway_requests(id)
                );
                CREATE INDEX IF NOT EXISTS idx_steps_req ON agentic_execution_steps(gateway_request_id);

                CREATE TABLE IF NOT EXISTS response_evaluations (
                    id TEXT PRIMARY KEY,
                    gateway_request_id TEXT NOT NULL,
                    overall_score REAL NOT NULL,
                    passed INTEGER NOT NULL,
                    relevance_score REAL,
                    adherence_score REAL,
                    completeness_score REAL,
                    code_score REAL,
                    format_score REAL,
                    should_escalate INTEGER,
                    escalation_reason TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(gateway_request_id) REFERENCES gateway_requests(id)
                );
                CREATE INDEX IF NOT EXISTS idx_evals_req ON response_evaluations(gateway_request_id);
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
            summary = dict(record.feature_summary)
            if hasattr(record, "complexity") and record.complexity:
                summary["complexity"] = record.complexity
            if hasattr(record, "strategy") and record.strategy:
                summary["strategy"] = record.strategy
            if hasattr(record, "alternative_eligible_models") and record.alternative_eligible_models:
                summary["alternative_eligible_models"] = record.alternative_eligible_models
            if hasattr(record, "estimated_cost") and record.estimated_cost is not None:
                summary["estimated_cost"] = record.estimated_cost
            if hasattr(record, "fallback_reason") and record.fallback_reason:
                summary["fallback_reason"] = record.fallback_reason

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
                    json.dumps(summary),
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

    async def get_usage_summary(self, since_timestamp: Optional[float] = None, limit: int = 100) -> dict:
        """Aggregates request volumes, tokens, latencies, and cache metrics."""
        async with self._get_conn() as conn:
            where_req = "WHERE created_at >= ?" if since_timestamp else ""
            params = (since_timestamp,) if since_timestamp else ()

            # Total requests, avg latency, cache counts
            cursor = await conn.execute(
                f"""
                SELECT
                    COUNT(*) as total_requests,
                    COALESCE(AVG(latency_ms), 0.0) as avg_latency_ms,
                    SUM(CASE WHEN cache_status = 'hit' THEN 1 ELSE 0 END) as cache_hits,
                    SUM(CASE WHEN fallback_used = 1 THEN 1 ELSE 0 END) as fallback_count
                FROM gateway_requests {where_req}
                """,
                params,
            )
            req_stats = await cursor.fetchone()
            total_requests = req_stats["total_requests"] if req_stats else 0
            avg_latency_ms = round(float(req_stats["avg_latency_ms"]), 2) if req_stats else 0.0
            cache_hits = req_stats["cache_hits"] if req_stats else 0
            fallback_count = req_stats["fallback_count"] if req_stats else 0
            cache_hit_rate = round(cache_hits / total_requests, 4) if total_requests > 0 else 0.0

            # Token statistics from usage_records
            token_query = f"""
                SELECT
                    COALESCE(SUM(u.input_tokens), 0) as total_input_tokens,
                    COALESCE(SUM(u.output_tokens), 0) as total_output_tokens,
                    COALESCE(SUM(u.total_tokens), 0) as total_tokens
                FROM usage_records u
                JOIN gateway_requests r ON u.gateway_request_id = r.id
                {where_req}
            """
            cursor = await conn.execute(token_query, params)
            token_stats = await cursor.fetchone()
            input_tokens = token_stats["total_input_tokens"] if token_stats else 0
            output_tokens = token_stats["total_output_tokens"] if token_stats else 0
            total_tokens = token_stats["total_tokens"] if token_stats else 0

            # Policy breakdown
            cursor = await conn.execute(
                f"SELECT routing_policy, COUNT(*) as count FROM gateway_requests {where_req} GROUP BY routing_policy",
                params,
            )
            policy_rows = await cursor.fetchall()
            policy_breakdown = {row["routing_policy"] or "adaptive": row["count"] for row in policy_rows}

            # Model breakdown
            cursor = await conn.execute(
                f"SELECT final_model_alias, COUNT(*) as count FROM gateway_requests {where_req} GROUP BY final_model_alias",
                params,
            )
            model_rows = await cursor.fetchall()
            model_breakdown = {row["final_model_alias"] or "unknown": row["count"] for row in model_rows}

            # Recent requests
            cursor = await conn.execute(
                f"""
                SELECT id, trace_id, created_at, routing_policy, final_model_alias, status, latency_ms, cache_status
                FROM gateway_requests {where_req}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (*params, limit),
            )
            recent_rows = await cursor.fetchall()
            recent_requests = [
                {
                    "id": row["id"],
                    "trace_id": row["trace_id"],
                    "created_at": row["created_at"],
                    "policy": row["routing_policy"],
                    "model": row["final_model_alias"],
                    "status": row["status"],
                    "latency_ms": row["latency_ms"],
                    "cached": row["cache_status"] == "hit",
                }
                for row in recent_rows
            ]

            return {
                "total_requests": total_requests,
                "total_input_tokens": input_tokens,
                "total_output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "avg_latency_ms": avg_latency_ms,
                "cache_hits": cache_hits or 0,
                "cache_hit_rate": cache_hit_rate,
                "fallback_count": fallback_count or 0,
                "policy_breakdown": policy_breakdown,
                "model_breakdown": model_breakdown,
                "recent_requests": recent_requests,
            }

    async def get_cost_summary(self, since_timestamp: Optional[float] = None) -> dict:
        """Aggregates cost metrics across providers, models, and calculation status."""
        async with self._get_conn() as conn:
            where_req = "WHERE r.created_at >= ?" if since_timestamp else ""
            params = (since_timestamp,) if since_timestamp else ()

            # Total spend and status
            cursor = await conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(u.estimated_cost), 0.0) as total_spend,
                    COALESCE(SUM(CASE WHEN u.cost_status = 'calculated' THEN u.estimated_cost ELSE 0.0 END), 0.0) as calculated_spend,
                    COALESCE(SUM(CASE WHEN u.cost_status = 'estimated' THEN u.estimated_cost ELSE 0.0 END), 0.0) as estimated_spend,
                    u.currency
                FROM usage_records u
                JOIN gateway_requests r ON u.gateway_request_id = r.id
                {where_req}
                GROUP BY u.currency
                """,
                params,
            )
            cost_row = await cursor.fetchone()
            total_spend = round(float(cost_row["total_spend"]), 6) if cost_row else 0.0
            calculated_spend = round(float(cost_row["calculated_spend"]), 6) if cost_row else 0.0
            estimated_spend = round(float(cost_row["estimated_spend"]), 6) if cost_row else 0.0
            currency = cost_row["currency"] if cost_row else "USD"

            # Spend by model
            cursor = await conn.execute(
                f"""
                SELECT
                    r.final_model_alias,
                    COALESCE(SUM(u.estimated_cost), 0.0) as spend,
                    COALESCE(SUM(u.total_tokens), 0) as tokens,
                    COUNT(r.id) as request_count
                FROM gateway_requests r
                LEFT JOIN usage_records u ON r.id = u.gateway_request_id
                {where_req}
                GROUP BY r.final_model_alias
                """,
                params,
            )
            model_rows = await cursor.fetchall()
            model_spend = {
                row["final_model_alias"] or "unknown": {
                    "spend": round(float(row["spend"]), 6),
                    "tokens": row["tokens"],
                    "requests": row["request_count"],
                }
                for row in model_rows
            }

            # Spend by provider
            cursor = await conn.execute(
                f"""
                SELECT
                    r.final_provider,
                    COALESCE(SUM(u.estimated_cost), 0.0) as spend,
                    COUNT(r.id) as request_count
                FROM gateway_requests r
                LEFT JOIN usage_records u ON r.id = u.gateway_request_id
                {where_req}
                GROUP BY r.final_provider
                """,
                params,
            )
            provider_rows = await cursor.fetchall()
            provider_spend = {
                row["final_provider"] or "unknown": {
                    "spend": round(float(row["spend"]), 6),
                    "requests": row["request_count"],
                }
                for row in provider_rows
            }

            return {
                "total_spend": total_spend,
                "calculated_spend": calculated_spend,
                "estimated_spend": estimated_spend,
                "currency": currency or "USD",
                "model_breakdown": model_spend,
                "provider_breakdown": provider_spend,
            }

    async def get_recent_decisions(self, limit: int = 20) -> list:
        """Retrieves recent routing decisions with request context."""
        async with self._get_conn() as conn:
            cursor = await conn.execute(
                """
                SELECT
                    d.id as decision_id,
                    d.gateway_request_id,
                    d.policy_name,
                    d.policy_version,
                    d.selected_provider,
                    d.selected_model_alias,
                    d.tier,
                    d.reason_code,
                    d.reason_message,
                    d.feature_summary_json,
                    d.created_at,
                    r.trace_id,
                    r.latency_ms,
                    r.status as request_status,
                    r.fallback_used,
                    u.estimated_cost,
                    u.total_tokens
                FROM routing_decisions d
                JOIN gateway_requests r ON d.gateway_request_id = r.id
                LEFT JOIN usage_records u ON r.id = u.gateway_request_id
                ORDER BY d.created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            decisions = []
            for row in rows:
                features = {}
                try:
                    if row["feature_summary_json"]:
                        features = json.loads(row["feature_summary_json"])
                except Exception:
                    features = {}

                decisions.append({
                    "decision_id": row["decision_id"],
                    "trace_id": row["trace_id"],
                    "policy": row["policy_name"],
                    "policy_version": row["policy_version"],
                    "selected_provider": row["selected_provider"],
                    "selected_model": row["selected_model_alias"],
                    "tier": row["tier"],
                    "reason_code": row["reason_code"],
                    "reason": row["reason_message"],
                    "features": features,
                    "complexity": features.get("complexity", "SIMPLE"),
                    "strategy": features.get("strategy", "balanced"),
                    "alternative_eligible_models": features.get("alternative_eligible_models", []),
                    "fallback_reason": features.get("fallback_reason"),
                    "latency_ms": row["latency_ms"] or 0,
                    "total_tokens": row["total_tokens"] or 0,
                    "cost_estimate": row["estimated_cost"],
                    "fallback_used": bool(row["fallback_used"]),
                    "created_at": row["created_at"],
                })
            return decisions

