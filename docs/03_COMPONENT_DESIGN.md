# 03. Component Design and Ownership

| Component | Owns | Must not own |
|---|---|---|
| API controller | HTTP parsing, auth, validation, status codes, response envelope | Routing heuristics, provider-specific parsing |
| Request normalizer | Canonical message/options representation | External API calls |
| Routing engine | Complexity features, policy selection, explanation | HTTP, database connections, model inference |
| Request orchestrator | Coordinates cache, router, adapter, retries, persistence | Provider-specific payload details |
| Provider adapter | Provider request/response translation and error mapping | Business routing policy |
| Retry/fallback policy | Retryability, attempt budget, backoff, fallback eligibility | Infinite retry or arbitrary model selection |
| Cache service | Key derivation, TTL, get/set, eligibility checks | Persisting usage or bypassing auth controls |
| Usage/cost service | Token normalization and rate-card calculation | Guessing missing token counts or prices |
| Trace repository | Durable request, attempt, route, and usage records | Logging secrets or raw auth headers |
| Benchmark agent | Executes defined benchmark tasks and uses approved tools | Changing expected answers or scorer results |
| Evaluator/scorer | Scores output and trajectory against dataset rubric | Modifying model outputs to improve scores |
| Report generator | Aggregates policy results and limitations | Inventing missing measurements |

## Domain objects

- `GatewayRequest`: canonical application request.
- `RoutingFeatures`: deterministic features extracted from the request.
- `RoutingDecision`: selected model/tier, policy version, reason, and fallback eligibility.
- `ProviderAttempt`: one attempt to contact one provider/model.
- `NormalizedCompletion`: provider-neutral content, finish reason, usage, and provider metadata.
- `RequestTrace`: one logical gateway request and its linked attempts.
- `UsageRecord`: token counts and cost-estimate metadata.
- `EvaluationCase`: versioned input, expected outcome, allowed tools, and scoring rubric.
- `EvaluationRun`: dataset/policy/model/prompt version and aggregate results.

## Dependency direction

HTTP/API -> application orchestration -> domain interfaces. Infrastructure adapters (provider, database, cache) implement interfaces consumed by application/domain logic. Domain policy must not import FastAPI, a provider SDK, or database-specific code.

## Suggested package layout (implementation agent may refine names)

```text
app/
  api/              # routes, dependencies, request/response schemas
  core/             # settings, logging, error types
  domain/           # routing, cost, retry, cache policy, entities
  services/         # orchestration and application use cases
  providers/        # adapter interface and provider implementations
  repositories/     # persistence interfaces and implementations
  observability/    # trace events, metrics, redaction
  evaluation/       # agent, tools, dataset loader, scorers, runner, reports
  tests/            # unit, integration, contract tests
```

This is a logical layout, not a requirement to create empty modules upfront.
