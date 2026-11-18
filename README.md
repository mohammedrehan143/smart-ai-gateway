# Smart AI Gateway

**Production-Grade AI Gateway with Intelligent Routing, True BYOK Multi-Tenant Isolation, Enterprise Security, and Observability.**

[![CI Pipeline](https://github.com/gateai/smart-ai-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/gateai/smart-ai-gateway/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Test Suite](https://img.shields.io/badge/tests-151%20passed-brightgreen.svg)](tests/)
[![Routing Accuracy](https://img.shields.io/badge/routing%20accuracy-100%25-success.svg)](evaluation_dataset/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 1. Product Overview

**Smart AI Gateway** centralizes model access, intelligent model selection, operational observability, and reliability across AI providers behind an OpenAI-compatible interface (`POST /v1/chat`).

It automatically routes simple queries to fast, cost-effective models (e.g., Llama 3.1 8B, GPT-4o-mini) and complex engineering/reasoning queries to advanced models (e.g., GPT-4o, Claude 3.5 Sonnet, o1) — delivering **62.5%+ cost savings** while preserving response quality.

### Core Architecture Highlights

1. **Intelligent Auto-Routing Engine**: Multi-dimensional complexity classifier (Simple, Moderate, Complex, Expert) with an explicit **conversation history isolation guarantee** (the latest turn is the primary signal; prior context never inflates complexity). Evaluated to **100% routing accuracy** on a 30-prompt benchmark dataset.
2. **True BYOK (Bring Your Own Key) Multi-Tenant Credential Store**: Strictly isolated per tenant. Users can securely configure, encrypt, test, and rotate keys for OpenAI, Groq, Google Gemini, Anthropic, and OpenAI-compatible providers.
3. **Enterprise Security**:
   - Zero-trust authentication with constant-time comparison (`secrets.compare_digest`).
   - Brute-force lockout and sliding-window rate limiting per IP and per tenant.
   - Dedicated master encryption key (`ENCRYPTION_MASTER_KEY`) utilizing Fernet/AES-256 with key rotation and re-encryption.
   - SSRF protection on custom provider endpoints (blocks RFC 1918 private subnets, loopback, link-local, AWS/GCP cloud metadata, and mitigates DNS rebinding).
   - Strict CORS configuration (wildcards strictly prohibited in production).
   - Payload size limiters (1MB default) and security headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options).
4. **Provider Execution & Resiliency**:
   - Bounded exponential backoff with jitter and `Retry-After` header compliance.
   - Circuit breaker tracking per model and provider.
   - Connection pooling (`httpx.AsyncClient` keep-alive).
   - Fallback model progression without silent mock execution in production.
5. **Observability & LLMOps**: Full asynchronous trace persistence to SQLite/PostgreSQL with token provenance, exact rate cards, cost calculations, and OpenTelemetry-compatible headers.
6. **Unified Developer Experience**: High-performance REST API, interactive ChatGPT-style Web Playground, and native `smartai` CLI.

---

## 2. System Architecture

```mermaid
flowchart TD
    Client[Client App / CLI / Web UI] -->|POST /v1/chat| Ingress[Security & Limits Middleware]
    Ingress --> Auth[Constant-Time Auth & Rate Limiter]
    Auth --> TenantGuard[Tenant Identity Enforcer]
    TenantGuard --> SemanticCache{Two-Tier Cache Hit?}
    SemanticCache -- Yes --> TracePersist[Persist Trace & Usage]
    TracePersist --> Return[Return Cached Normalized Response]
    SemanticCache -- No --> FeatureEngine[Feature Extractor & Intent Engine]
    FeatureEngine --> Classifier[Complexity Classifier: Simple / Moderate / Complex / Expert]
    Classifier --> Router[Unified Routing Engine]
    Router --> BYOK[BYOK Credential Manager]
    BYOK --> SSRF[SSRF Validator & URL Resolver]
    SSRF --> Circuit[Circuit Breaker Registry]
    Circuit --> ExecEngine[Provider Manager: Connection Pool + Backoff]
    ExecEngine -->|Transient Error| Retry[Exponential Backoff + Jitter]
    Retry --> ExecEngine
    ExecEngine -->|Hard Outage| Fallback[Candidate Fallback Progression]
    Fallback --> ExecEngine
    ExecEngine --> Sanitizer[Response Sanitizer & Cost Calculator]
    Sanitizer --> TracePersist
    TracePersist --> ReturnSuccess[Return Normalized Envelope + Provenance]
```

---

## 3. Production Security & Invariants

| Security Control | Implementation Details |
|---|---|
| **Production Fail-Fast** | `settings.validate_production_security()` halts gateway startup if `GATEWAY_API_KEY` or `ENCRYPTION_MASTER_KEY` is missing, shorter than 16 chars, or if wildcard CORS is enabled. |
| **Authentication** | Bearer tokens validated using `secrets.compare_digest` to prevent timing attacks. Support for token rotation (`ALLOWED_API_KEYS`) and immediate revocation (`REVOKED_API_KEYS`). |
| **Tenant Isolation** | Never trusts unauthenticated `X-User-ID`. User identity is strictly derived from verified tokens. Tenants cannot view, execute, or delete each other's credentials or cache entries. |
| **Credential Encryption** | Master encryption key independent of gateway authentication. Dedicated Fernet ciphers with multi-key rotation (`rotate_ciphertext`). API keys are masked (`sk-...4f8b`) in all logs and API responses. |
| **SSRF Defense** | All custom provider `base_url` values are verified before storage and dispatch. Blocks RFC 1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.1`), link-local (`169.254.0.0/16`), AWS/GCP metadata (`169.254.169.254`, `metadata.google.internal`), and re-resolves DNS to mitigate rebinding. |
| **Rate Limiting** | In-memory sliding window rate limiter (120 RPM default) and automatic 15-minute brute-force IP lockout after 5 consecutive failed authentication attempts. |
| **Mock Blocking** | Mock execution mode (`MockProviderAdapter`) is strictly disallowed in production; genuine provider credentials or BYOK keys are enforced. |

---

## 4. Intelligent Routing Architecture

The routing pipeline deterministically selects between **Weak/Cheap** and **Strong/Advanced** agents:

```
Request -> Preprocessing -> Intent Detection -> Complexity Classification -> Task Categorization -> Capability Matching -> Budget Check -> BYOK Resolver -> Execution & Fallback
```

### Routing Signals & Decision Criteria
- **Reasoning Complexity**: Security incident forensics, formal proofs, distributed systems architecture $\rightarrow$ Strong Agent (`gpt-4o`, `claude-3-5-sonnet`).
- **Coding Difficulty**: Multi-threaded concurrency debugging, deadlocks, race conditions $\rightarrow$ Strong Agent.
- **Routine Knowledge**: Definitions, factual lookups, greetings, basic string manipulation, standard math $\rightarrow$ Weak Agent (`llama-3.1-8b-instant`, `gpt-4o-mini`).
- **History Isolation Guarantee**: Multi-turn conversations classify the **latest user turn as the primary signal**. If Turn 1 was a complex architecture design and Turn 2 is "Hi", Turn 2 is guaranteed to route to the Weak Agent.

### Evaluation Accuracy
The routing engine is verified against `evaluation_dataset/routing_eval_dataset_v1.json`:
- **Tier Routing Accuracy**: **100.0%** (30/30)
- **Complexity Classification Accuracy**: **100.0%** (30/30)

---

## 5. Quickstart & Installation

### Option A: Automated Production Script

#### Windows (PowerShell):
```powershell
.\deployment\deploy.ps1
```

#### Linux / macOS:
```bash
chmod +x ./deployment/deploy.sh
./deployment/deploy.sh
```

The script automatically detects Docker (running containerized with Compose) or falls back to native production Uvicorn with automated health check verification.

---

### Option B: Manual Local Setup

```bash
# 1. Clone repository and navigate
cd smart-ai-gateway

# 2. Activate virtual environment
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
# source .venv/bin/activate    # Linux/macOS

# 3. Install dependencies
pip install -r requirements-dev.txt
pip install -e .

# 4. Copy environment configuration
cp .env.example .env

# 5. Start development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive Swagger documentation is available at `http://localhost:8000/docs`, and the Web Playground is at `http://localhost:8000/`.

---

## 6. BYOK (Bring Your Own Key) Management

Users and tenants can securely manage provider API credentials via REST endpoints:

### Store Provider Credential
```bash
curl -X POST http://localhost:8000/v1/credentials \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "groq",
    "api_key": "gsk_your_groq_api_key_here",
    "base_url": "https://api.groq.com/openai/v1"
  }'
```

### List Stored Credentials (Masked)
```bash
curl -X GET http://localhost:8000/v1/credentials \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY"
```

Response:
```json
[
  {
    "provider": "groq",
    "masked_key": "gsk...4f8b",
    "base_url": "https://api.groq.com/openai/v1",
    "is_active": true,
    "created_at": 1794050120.5,
    "updated_at": 1794050120.5
  }
]
```

### Delete / Revoke Credential
```bash
curl -X DELETE http://localhost:8000/v1/credentials/groq \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY"
```

---

## 7. Smart AI CLI Guide (`smartai`)

```bash
# Login and store gateway credentials in OS Keyring
smartai login

# Check gateway health and latency
smartai status

# Interactive multi-turn chat with live streaming
smartai chat

# One-shot intelligent prompt execution
smartai ask "Design a high-throughput microservices architecture"

# Inspect recent routing decisions & feature extractions
smartai route --limit 10

# Inspect usage & spend telemetry
smartai usage --hours 24
smartai cost --hours 48

# Run automated benchmark evaluation
smartai benchmark --samples 21 --export docs/BENCHMARK_REPORT.md
```

---

## 8. Verification & Test Suite

The gateway includes comprehensive test coverage across unit, integration, security, routing regression, and reliability tests:

```bash
# Run complete test suite (151 tests)
pytest -v

# Run security hardening tests
pytest tests/security/ -v

# Run multi-turn routing regression tests
pytest tests/integration/test_multi_turn_routing_regression.py -v

# Run routing benchmark evaluation dataset
pytest tests/unit/test_routing_eval_dataset.py -v -s

# Run code style & linting checks
ruff check app/ tests/ agents/ smart_ai_cli/
ruff format --check app/ tests/ agents/ smart_ai_cli/

# Run Master Orchestrator phase verification
python scripts/master_orchestrator.py run-all
```

---

## 9. Key Rotation & Migration Guide

When rotating your encryption master key:
1. Generate a new 32-byte urlsafe Fernet key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. Move your current `ENCRYPTION_MASTER_KEY` to `ENCRYPTION_PREVIOUS_KEYS`:
   ```bash
   ENCRYPTION_PREVIOUS_KEYS=old-master-key-here
   ENCRYPTION_MASTER_KEY=new-master-key-here
   ```
3. Restart the gateway. The cryptographic engine automatically decrypts existing ciphertexts using `ENCRYPTION_PREVIOUS_KEYS` and re-encrypts updated credentials using the new `ENCRYPTION_MASTER_KEY`.
