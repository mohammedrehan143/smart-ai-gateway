# Production Readiness Guide: Smart AI Gateway

This document provides the operational blueprint, configuration checklist, security hardening guidelines, and infrastructure setups required to deploy **Smart AI Gateway** into production environments.

---

## 1. Production Architecture Overview

In production, the gateway transitions from single-process development mode to a distributed, horizontally scalable architecture:

```mermaid
flowchart TD
    Client[Client Applications / SDKs] -->|HTTPS:443| Ingress[Nginx Reverse Proxy / Cloud Load Balancer]
    Ingress -->|Rate Limiting & SSL Termination| GW1[Gateway Instance 1]
    Ingress -->|Rate Limiting & SSL Termination| GW2[Gateway Instance 2]
    
    subgraph Data Tier
        GW1 & GW2 -->|Distributed Cache & Quotas| Redis[(Redis Cluster)]
        GW1 & GW2 -->|Traces, Usage & Audit Logs| Postgres[(PostgreSQL 16 Primary)]
        Postgres -->|Async Replication| Replica[(PostgreSQL Read Replica)]
    end
    
    subgraph External LLM Providers
        GW1 & GW2 -->|Async TLS 1.3 / Bounded Retries| P1[OpenAI API]
        GW1 & GW2 -->|Fallback| P2[Secondary Provider / Model]
    end

    subgraph Observability
        Prom[Prometheus] -->|Scrape /metrics| GW1 & GW2
        Prom --> Grafana[Grafana Dashboard]
        GW1 & GW2 -->|JSON Logs| LogCollector[Datadog / Vector / CloudWatch]
    end
```

---

## 2. Production Environment Configuration (`.env.production`)

Set the following environment variables in your deployment secret manager (AWS Secrets Manager, GCP Secret Manager, or HashiCorp Vault):

```ini
# Application Identity
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO

# Security & Gateway Authentication (MANDATORY)
GATEWAY_API_KEY=gw_live_a89f72b94c03d891e23f044917a2
ALLOWED_CORS_ORIGINS=["https://app.yourcompany.com", "https://api.yourcompany.com"]
MAX_REQUEST_BODY_BYTES=1048576  # 1 MB max payload
RATE_LIMIT_RPM=120

# High-Availability Persistence
DATABASE_URL=postgresql://gateway_user:StrongPasswordHere@postgres-cluster.internal:5432/gateway_db

# High-Availability Shared Caching
CACHE_BACKEND=memory            # Or 'redis' for multi-instance
CACHE_TTL_SECONDS=300
REDIS_URL=redis://:RedisPasswordHere@redis-cluster.internal:6379/0

# Model Registry Aliases
CHEAP_MODEL_ALIAS=gpt-4o-mini
STRONG_MODEL_ALIAS=gpt-4o
FALLBACK_MODEL_ALIAS=gpt-4o

# Hosted Provider Credentials
PROVIDER_API_KEY=sk-proj-LiveHostedKeyHere...
PROVIDER_BASE_URL=https://api.openai.com/v1

# Resiliency Deadlines
REQUEST_TIMEOUT_SECONDS=30.0
MAX_PROVIDER_ATTEMPTS=3
```

---

## 3. Production Deployment Options

### Option A: Docker Compose (Single Host / Small Team)

The repository provides [docker-compose.prod.yml](file:///D:/agy/gateai/smart-ai-gateway/docker-compose.prod.yml) with PostgreSQL, Redis, Nginx, and the hardened Gateway container.

```bash
# 1. Create TLS certificates
mkdir -p deployment/certs
# Place fullchain.pem and privkey.pem into deployment/certs/

# 2. Launch production stack
docker compose -f docker-compose.prod.yml up --build -d

# 3. Verify health
curl -f https://localhost/health/live
```

### Option B: Cloud Container Deployment (AWS ECS, GCP Cloud Run, Kubernetes)

1. **Build and push image:**
   ```bash
   docker build -t your-registry.io/smart-ai-gateway:v0.1.0 .
   docker push your-registry.io/smart-ai-gateway:v0.1.0
   ```
2. **Kubernetes Health Probes:**
   * **Liveness:** `GET /health/live` (initial delay: 5s, period: 10s)
   * **Readiness:** `GET /health/ready` (initial delay: 5s, period: 10s)
3. **Resource Limits:**
   * Requests: `cpu: 250m`, `memory: 256Mi`
   * Limits: `cpu: 1000m`, `memory: 512Mi`

---

## 4. Security Hardening Checklist

- [x] **Constant-Time Token Comparison:** `secrets.compare_digest` in `app/api/deps.py` prevents timing side-channel attacks on `GATEWAY_API_KEY`.
- [x] **Payload Size Limits:** `MAX_REQUEST_BODY_BYTES` (default 1 MB) protects memory from buffer overflow or payload exhaustion attacks.
- [x] **HTTP Security Headers:** Natively sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security`, and `X-XSS-Protection`.
- [x] **CORS Whitelist:** Explicit `ALLOWED_CORS_ORIGINS` prevents unauthorized cross-origin browser requests.
- [x] **Redaction:** Recursive logger redaction strips `Authorization`, `api_key`, `token`, and `secret` parameters from stdout/stderr.
- [x] **Prompt Privacy:** Message content is not stored in plain database logs by default unless `STORE_PROMPT_CONTENT=true` is explicitly requested.

---

## 5. Monitoring & Alerting (Prometheus & Grafana)

The gateway exports real-time metrics at `GET /metrics`:

### Metric Reference

| Metric Name | Type | Description |
|---|---|---|
| `gateway_requests_total` | Counter | Total requests segmented by `{policy, model, status}` |
| `gateway_tokens_total` | Counter | Total tokens segmented by `{type="input"|"output"}` |
| `gateway_estimated_cost_usd` | Counter | Cumulative estimated spend in USD |
| `gateway_cache_events_total` | Counter | Segmented by `{type="hit"|"miss"}` |
| `gateway_fallbacks_total` | Counter | Count of fallback activations |
| `gateway_latency_ms` | Gauge | Quantiles: `0.50` (p50) and `0.95` (p95) latency |

### Recommended Alerting Rules

1. **High Error Rate:** Alert when 5xx errors exceed 2% of total traffic over a 5-minute window.
2. **Fallback Surge:** Alert if `gateway_fallbacks_total` rate > 5 per minute (signals primary provider degradation).
3. **P95 Latency Spike:** Alert when `gateway_latency_ms{quantile="0.95"}` > 5000ms over 3 consecutive evaluation cycles.
4. **Spend Acceleration:** Alert if hourly cost exceeds defined budget threshold (e.g., > $10.00/hour).

---

## 6. Zero-Downtime Migration & Rollback Runbook

1. **Database Schema Changes:** All table changes (`gateway_requests`, `provider_attempts`) must be backwards-compatible and additive.
2. **Rolling Deploys:** Deploy new gateway containers, wait for `/health/ready` to pass, then drain old instances.
3. **Emergency Rollback:** If high upstream error rates or configuration faults occur:
   ```bash
   # Revert to previous image tag immediately
   docker compose -f docker-compose.prod.yml down
   # Point image to previous git SHA tag
   docker compose -f docker-compose.prod.yml up -d
   ```
