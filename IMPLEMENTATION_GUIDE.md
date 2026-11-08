# Implementation Guide for the Coding Agent

## Objective

Implement the system described by this specification without changing the product boundaries or inventing features. Treat the docs in `docs/` as the source of truth and the agent instructions in `agents/` as role-specific execution constraints.

## Required implementation order

1. Project skeleton, configuration, logging, and health checks.
2. Provider adapter interface and mocked provider.
3. `POST /v1/chat` request validation and normalized response.
4. Persistence for request traces and usage.
5. Real hosted provider adapter and cost-rate configuration.
6. Deterministic router with unit tests and explainable decision output.
7. Retry/fallback and cache.
8. Runtime benchmark agent and deterministic tools.
9. Versioned task dataset and scorers.
10. Benchmark runner for three policies and report export.
11. Docker, CI, deployment notes, operational runbooks.

## Engineering constraints

- Use Python type hints throughout. Prefer small modules with clear ownership.
- Use FastAPI and async `httpx` for network I/O.
- Use Pydantic models for external request/response validation.
- Keep provider-specific payload mapping inside provider adapters.
- Keep routing policy independent of provider SDKs and model-specific HTTP details.
- Keep scoring logic independent of the model invocation logic.
- Store configuration outside source code. Never commit secrets.
- Add tests with each component; do not postpone all tests until the end.
- Use structured logs and correlation IDs.
- Do not log API keys, authorization headers, or unredacted sensitive content.
- Do not claim measured token cost if provider usage or a configured rate is missing.

## Architecture guardrails

- The router is a deterministic module/function, not an LLM call.
- The gateway is stateless between requests except for persistence/cache infrastructure.
- The evaluation runner calls the same public gateway path as an application client.
- The benchmark agent's tools must be deterministic and controlled by test fixtures.
- Provider adapters implement a common interface; business logic must not branch on raw provider SDK response shapes.
- Every routing decision must record policy version, selected model, tier, and human-readable reason.

## Acceptance workflow

For each milestone: implement -> add/update tests -> run lint/type checks -> update docs if contracts changed -> report files changed and tests executed. Do not move to the next milestone with failing tests or undocumented contract changes.

## Required handoff at completion

Provide setup instructions, environment variable reference, architecture diagram, API examples, test commands, benchmark command, a sample report generated from actual runs, deployment steps, known limitations, and a list of all configuration values that still need the developer's credentials or choices.
