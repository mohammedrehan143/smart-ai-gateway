# 01. Product Requirements

## 1. Product overview

Smart AI Gateway is a backend infrastructure service between an application and hosted LLM providers. It centralizes provider access, routing, reliability controls, telemetry, and quality evaluation.

## 2. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | Accept a validated chat request at `POST /v1/chat`. | Must |
| FR-02 | Select a model through a deterministic routing policy. | Must |
| FR-03 | Allow only models present in server-side configuration/allowlist. | Must |
| FR-04 | Invoke providers through a common adapter interface. | Must |
| FR-05 | Normalize provider responses into one gateway response contract. | Must |
| FR-06 | Apply bounded retries to retryable network/provider failures. | Must |
| FR-07 | Fall back to an approved alternate model when the active policy permits. | Must |
| FR-08 | Cache eligible successful responses with TTL and cache-safety rules. | Should |
| FR-09 | Persist trace, token usage, latency, route, retry/fallback, and outcome fields. | Must |
| FR-10 | Calculate cost estimates from a versioned model rate card. | Must |
| FR-11 | Run a benchmark agent with calculator and deterministic lookup tools. | Must |
| FR-12 | Score answer correctness, tool selection/use, and trace/step quality. | Must |
| FR-13 | Compare always-cheap, always-strong, and adaptive policies on the same tasks. | Must |
| FR-14 | Produce a report with quality, cost, latency, and reliability metrics. | Must |
| FR-15 | Expose liveness and readiness health endpoints. | Should |

## 3. Non-functional requirements

- **Reliability:** Provider failure must result in a bounded retry/fallback path or a clear normalized error; no infinite retries.
- **Performance:** Gateway overhead should be measured separately from model latency. Do not invent an absolute latency target before baseline measurements.
- **Maintainability:** Provider integrations and routing policy must be independently testable.
- **Security:** Secrets are injected at runtime; logs and traces redact credentials and configured sensitive fields.
- **Portability:** Local development and deployment use the same application container contract.
- **Resource efficiency:** Local components must run within a modest laptop environment; inference remains hosted.
- **Auditability:** Every route choice and benchmark run is reproducible from a versioned policy/config/task-set identifier.

## 4. Primary user journeys

### Application developer
1. Configures gateway base URL and API key.
2. Sends a chat request to `/v1/chat`.
3. Receives a normalized response and trace ID.
4. Uses the trace ID to investigate issues (via logs/admin tooling in later scope).

### AI engineer
1. Configures approved cheap and strong model tiers.
2. Runs a fixed evaluation set under three policies.
3. Reviews pass rate, cost, latency, routing distribution, and failure rate.
4. Adjusts thresholds and repeats the benchmark with a new policy version.

### Operator
1. Checks readiness and provider health indicators.
2. Inspects errors, retries, fallbacks, usage, and cost trends.
3. Updates provider secrets/rate cards through deployment configuration.

## 5. Product constraints

The first version should not introduce a frontend dashboard as a prerequisite. Reports may be exported as JSON/CSV/Markdown and inspected locally. A dashboard is a later presentation layer, not a core dependency.
