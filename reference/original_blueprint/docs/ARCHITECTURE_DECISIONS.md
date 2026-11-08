# Architecture Decision Records

This file records current proposed decisions. Revisit them when implementation evidence changes.

## ADR-001: Start as a modular monolith

**Decision:** Build one FastAPI service with clear internal modules.

**Reason:** A single developer can implement and debug it faster. Service decomposition adds deployment and networking overhead before it is needed.

## ADR-002: Use a canonical provider interface

**Decision:** All providers implement the same internal request/response contract.

**Reason:** Routing and reliability should not depend on vendor-specific schemas.

## ADR-003: Begin with rule-based routing

**Decision:** Use transparent deterministic rules before any learned classifier.

**Reason:** It is explainable, testable, and creates a baseline against which future routing approaches can be measured.

## ADR-004: Keep evaluation separate from production routing

**Decision:** Evaluation runner and scorers are separate modules that invoke the gateway through its public contract.

**Reason:** This reduces the risk of tests bypassing real routing behavior.

## ADR-005: Report unknown cost/usage as unknown

**Decision:** Missing provider usage or price information is nullable and labeled.

**Reason:** Treating missing values as zero creates misleading cost claims.

## ADR-006: SQLite first, PostgreSQL for deployment

**Decision:** Use SQLite for local MVP and PostgreSQL when concurrent deployment or hosted persistence requires it.

**Reason:** Keeps early setup lightweight without locking the data model to SQLite.

## ADR-007: Cache conservatively

**Decision:** Cache only eligible requests with a complete cache key and defined retention.

**Reason:** Unrestricted caching can leak data or return stale/inappropriate answers.
