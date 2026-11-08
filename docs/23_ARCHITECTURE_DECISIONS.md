# 23. Architecture Decision Records (ADRs)

Keep this file updated when a decision changes. Each entry records context, decision, alternatives, and consequences.

## ADR-001: Modular monolith for MVP

- **Context:** Small project, modest local machine, limited operational budget.
- **Decision:** One FastAPI application with explicit module boundaries.
- **Alternatives:** Microservices, serverless functions.
- **Consequences:** Easier local development/testing; scale limits are acceptable for MVP.

## ADR-002: Deterministic routing first

- **Context:** Need explainable routing and a clean baseline for proving quality/cost trade-offs.
- **Decision:** Implement rule-based Python routing and record policy reasons/versions.
- **Alternatives:** LLM classifier, trained routing model.
- **Consequences:** Transparent and cheap; may be less nuanced, so tune using evaluation evidence.

## ADR-003: Hosted model inference

- **Context:** Developer machine has no discrete GPU and 8 GB RAM.
- **Decision:** Call hosted provider APIs through adapters; do not host or train a foundation model locally.
- **Alternatives:** Local model server.
- **Consequences:** Requires API credentials and internet; keeps local resource needs low.

## ADR-004: SQLite first, PostgreSQL for shared deployment

- **Context:** Need low-friction local setup but durable multi-instance deployment later.
- **Decision:** Repository abstraction with SQLite for local/dev and PostgreSQL for shared deployment.
- **Consequences:** Migration and SQL portability tests are needed.

## ADR-005: In-memory cache first, Redis when shared state is needed

- **Context:** Single-process demo does not need distributed cache infrastructure.
- **Decision:** Cache interface with bounded in-memory implementation first.
- **Consequences:** Cache is process-local; switch to Redis for multiple instances.

## ADR-006: Deterministic scorers first

- **Context:** Evaluation claims must be auditable and reproducible.
- **Decision:** Use exact/rubric/tool-trace checks first; any LLM judge is supplementary.
- **Consequences:** Some natural-language tasks require carefully written rubrics and human review.
