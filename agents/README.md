# Agent Specifications

This folder distinguishes **runtime product behaviour** from **development-time coding assistance**. They are not the same thing.

## Runtime agent

`runtime/BENCHMARK_AGENT_SPEC.md` defines the small tool-using agent that is actually evaluated by the product. It calls the gateway and uses only the approved benchmark tools.

## Development-time agents

The roles in `development/` are instructions for an AI coding assistant helping build or review the repository. They are not production microservices and must not be deployed as runtime agents.

| Role | Responsibility |
|---|---|
| Orchestrator | Enforce build order, delegate scoped work, maintain shared contracts, prevent scope drift. |
| Architect | Translate specifications into module boundaries, interfaces, and ADRs. |
| Implementation | Implement one approved milestone and its tests. |
| Router reviewer | Independently review routing correctness, explainability, and benchmark safety. |
| Evaluation | Review dataset, scoring, experiment controls, and report integrity. |
| QA/reliability | Review tests, failure paths, retry deadlines, and regressions. |
| Observability/security | Review trace quality, cost provenance, redaction, and operational readiness. |

## Usage rules

1. Start with the Orchestrator and `prompts/MASTER_BUILD_PROMPT.md`.
2. Have the Architect inspect the specifications before code is generated.
3. Implement one roadmap phase at a time.
4. Require the QA role to test each phase before moving on.
5. Use the Router Reviewer and Evaluation role before accepting benchmark claims.
6. Keep the router as deterministic Python logic; do not delegate its decision to an LLM at runtime.
7. Every agent must report assumptions, changed files, tests run, test results, and known gaps.
