# 22. Implementation Roadmap

The source brief suggests roughly 2-3 weeks as a build estimate. Treat this as an indicative student-project plan, not a guarantee; finish each phase to its acceptance criteria before adding the next.

## Phase 1 — Gateway foundation

Deliver: project structure, validated settings, FastAPI service, `POST /v1/chat`, normalized contract, mocked provider, basic trace record, unit/integration tests.

Exit criteria: a mocked completion travels through the public endpoint and produces a trace without any external provider credential.

## Phase 2 — Provider integration and LLMOps

Deliver: one hosted provider adapter, model registry/configuration, provider usage extraction, versioned rate card, cost calculation, structured logs, latency/usage persistence.

Exit criteria: a manual smoke request returns normalized output and a queryable trace with token/cost provenance.

## Phase 3 — Reliability and cache

Deliver: timeout, bounded retry/backoff, fallback model, cache interface and in-memory implementation, cache eligibility and metrics.

Exit criteria: mocked tests prove retry, non-retryable handling, fallback, and cache behaviour.

## Phase 4 — Deterministic auto-routing

Deliver: cheap/strong model tiers, feature extraction, configurable thresholds, three routing policies, reason codes, policy-version logging.

Exit criteria: routing tests pass and every decision can be explained from its recorded features/reason.

## Phase 5 — Benchmark agent and evaluations

Deliver: benchmark agent, calculator and lookup tools, 20-50 versioned tasks, answer/tool/trajectory scorers, three-policy runner, result export.

Exit criteria: same task set runs under all policies and produces comparable cost, quality, latency, and reliability metrics.

## Phase 6 — Ship and demonstrate

Deliver: Docker image, CI pipeline, deployment, runbook, architecture diagram, README walkthrough, benchmark report, known limitations, and interview explanation.

Exit criteria: clean setup from documented steps; CI green; deployed smoke request successful; benchmark evidence saved.

## Prioritization

Do not build a dashboard, multi-agent swarm, semantic cache, Kubernetes deployment, or model-based router before Phase 6 is complete. Those are optional future extensions.
