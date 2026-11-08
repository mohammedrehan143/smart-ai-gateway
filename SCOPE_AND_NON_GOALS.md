# Scope and Non-Goals

## MVP scope

- One public chat-generation endpoint: `POST /v1/chat`.
- Request validation and normalized response envelope.
- Two configured model tiers: a lower-cost model and a stronger model, accessed through hosted APIs.
- Provider adapter interface with at least one real provider and a mocked provider for tests.
- Deterministic complexity/routing policy with a recorded reason.
- Retry with bounded exponential backoff and jitter for retryable failures.
- Fallback to an approved alternate model when policy permits.
- Response cache with a bounded TTL and safe cache key.
- Per-request trace and usage record: provider/model, route, token counts, latency, status, retries, fallback, and cost estimate.
- Small benchmark agent with two or three deterministic tools.
- Versioned benchmark set of 20-50 tasks.
- Three benchmark policies: always-cheap, always-strong, adaptive router.
- Scoring of final answer, tool selection/usage, and execution trace.
- Docker packaging, automated tests, CI checks, and deployment documentation.

## Explicit non-goals for the first release

- Training, fine-tuning, or hosting a foundation model.
- Building a general-purpose chatbot UI.
- Building a marketplace for model providers.
- A fully autonomous multi-agent system.
- LLM-based routing as the default policy.
- Multi-tenant billing, payment collection, or customer invoicing.
- Kubernetes, service mesh, distributed task queues, or multi-region deployment.
- Full prompt-management SaaS, semantic cache, or vector database.
- Production-grade secrets management beyond a deployment platform's environment/secret store.
- Calling arbitrary external tools from benchmark tasks.

## Later extensions (only after MVP evidence)

- PostgreSQL for shared/deployed persistence.
- Redis for shared cache and rate-limit state.
- Additional model providers and model-specific capability metadata.
- Circuit breaker and provider health scoring.
- Per-tenant quotas and usage limits.
- Async evaluation jobs and scheduled regression runs.
- Policy version management and shadow evaluation.
- LLM-assisted task classification as an experiment, always compared against deterministic routing.

## Scope control rule

A feature is accepted into MVP only if it directly supports the gateway lifecycle or the three-policies benchmark. Otherwise it belongs in a later extension or is rejected.
