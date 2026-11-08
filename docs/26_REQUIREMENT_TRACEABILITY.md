# 26. Requirement Traceability Matrix

This matrix connects product requirements to design documents and verification evidence. The implementation team should update the final column with the actual test names/paths once code exists.

| Requirement | Design reference | Verification evidence required |
|---|---|---|
| FR-01: Validated `POST /v1/chat` | `05_API_CONTRACT.md`, `03_COMPONENT_DESIGN.md` | API schema and status-mapping tests |
| FR-02: Deterministic routing | `06_ROUTING_POLICY.md` | Unit tests for each rule and policy mode |
| FR-03: Server-side model allowlist | `06_ROUTING_POLICY.md`, `13_SECURITY_AND_PRIVACY.md` | Tests that arbitrary caller model IDs are rejected |
| FR-04: Provider adapter interface | `07_PROVIDER_ADAPTERS.md` | Shared adapter contract test suite |
| FR-05: Normalized response | `05_API_CONTRACT.md`, `07_PROVIDER_ADAPTERS.md` | Provider response normalization tests |
| FR-06: Bounded retries | `08_RELIABILITY_AND_FAILURES.md`, `20_ERROR_TAXONOMY.md` | Retryable/non-retryable and deadline tests |
| FR-07: Approved fallback | `06_ROUTING_POLICY.md`, `08_RELIABILITY_AND_FAILURES.md` | Fallback success/failure and allowlist tests |
| FR-08: Response cache | `03_COMPONENT_DESIGN.md`, `08_RELIABILITY_AND_FAILURES.md` | Cache key, TTL, hit/miss, and outage tests |
| FR-09: Trace and usage persistence | `09_LLMOPS_AND_OBSERVABILITY.md`, `12_DATA_MODEL.md` | Integration test proving linked request/attempt/usage rows |
| FR-10: Versioned cost estimate | `18_COST_MODEL.md`, `12_DATA_MODEL.md` | Unit tests for units, effective dates, unknown usage/rates |
| FR-11: Benchmark agent and tools | `agents/runtime/` | Tool contract tests and one end-to-end fixture case |
| FR-12: Multi-dimensional evaluation | `10_EVALUATION_FRAMEWORK.md` | Scorer tests for answer, tool, and trajectory dimensions |
| FR-13: Three-policy comparison | `11_BENCHMARK_PROTOCOL.md` | Run artifact with same dataset version for all policies |
| FR-14: Benchmark report | `11_BENCHMARK_PROTOCOL.md` | Report schema/aggregation tests and saved real run |
| FR-15: Health endpoints | `05_API_CONTRACT.md`, `15_DEPLOYMENT_AND_OPERATIONS.md` | Liveness/readiness endpoint tests |

## Change-control rule

A requirement is not complete because its code exists. It is complete only when the verification evidence is repeatable and linked to the relevant requirement. If a requirement is changed, update this matrix, the originating requirements document, tests, and any affected ADRs in the same change.
