# Project Charter

## 1. Purpose

Build a small but production-minded AI infrastructure service that demonstrates three capabilities commonly needed by teams operating LLM-backed applications: model selection, operational visibility, and evidence-based agent evaluation.

## 2. Problem statement

Applications that call model providers directly often duplicate provider-specific code, lack a consistent record of token usage and cost, have limited failure handling, and cannot easily prove whether cheaper models or routing policies preserve task quality. This project centralizes those concerns behind a gateway and provides a repeatable evaluation method.

## 3. Product outcome

A developer can point an application or benchmark agent at the gateway rather than calling a model provider directly. The gateway selects an approved model, invokes it through an adapter, applies retries/fallback where appropriate, records a trace and usage data, and returns a normalized response. An evaluation runner then measures the same agent tasks under three policies.

## 4. Users and stakeholders

- **Application developer:** integrates one stable API rather than multiple provider APIs.
- **AI/ML engineer:** changes routing policy and examines the quality/cost trade-off.
- **Platform/operations engineer:** investigates latency, failures, retries, provider health, and spend.
- **Reviewer/interviewer:** verifies the architecture and inspects benchmark evidence.

## 5. Guiding principles

1. Measure before optimizing.
2. Prefer deterministic and explainable routing for the first release.
3. Treat provider integrations as replaceable adapters.
4. Keep credentials and sensitive prompts out of logs.
5. Keep evaluation tasks and scoring rules versioned.
6. Never claim a cost saving or quality score without a recorded evaluation run.
7. Keep the local developer experience lightweight; inference is hosted.

## 6. Success definition

The gateway accepts a request, routes it according to a documented policy, returns a normalized result, and records model, token, latency, cost-estimate, route, and outcome data. It handles configured retryable failures and fallback. A tool-using benchmark agent completes a fixed 20-50 task evaluation set. The same tasks are run under always-cheap, always-strong, and adaptive policies. The final report includes pass rate, estimated cost per task, latency distribution, fallback rate, and the measured quality gap.

## 7. Constraints

- Developer machine: Intel i5, 8 GB RAM, no discrete GPU.
- No local foundation model hosting or training.
- Use hosted model APIs and a small number of providers/models.
- Start with SQLite and in-memory caching; only add PostgreSQL/Redis when required.
- Keep the first release understandable and explainable in an interview.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Provider API changes | Adapter boundary, contract tests, pinned configuration, documented provider capabilities. |
| Rate limits or outages | Bounded retries, `Retry-After`, fallback, circuit breaker only when needed. |
| Misleading cost results | Versioned rate cards, source usage fields, clearly mark estimated/missing costs. |
| Unfair benchmark | Same task IDs, prompts, tools, limits, and scoring rubric across policies. |
| Overengineering | Deliver by roadmap; no Kubernetes, distributed queues, or model training in MVP. |
| Sensitive data leakage | Redaction, no API-key logging, limited prompt retention, access control before public deployment. |

## 9. Out of scope

See [`SCOPE_AND_NON_GOALS.md`](SCOPE_AND_NON_GOALS.md). The product is gateway infrastructure, not a consumer chatbot, general agent platform, model-training pipeline, or full commercial API management suite.
