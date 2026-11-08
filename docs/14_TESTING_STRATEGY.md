# 14. Testing Strategy

## 1. Test layers

### Unit tests

Test routing rules, feature extraction, fallback eligibility, retryability classification, cost calculations, cache-key construction, request validation, scoring functions, and data normalization without network access.

### Provider contract tests

Mock HTTP interactions for every adapter: valid completion, usage missing, authentication failure, rate limit, timeout, server error, invalid JSON, and provider-specific response quirks.

### Integration tests

Run FastAPI with a test database and mocked provider. Verify request -> route -> attempt -> trace/usage persistence -> normalized response. Test retry/fallback, cache hit/miss, and trace persistence degradation.

### Evaluation tests

Use a tiny deterministic fixture set to verify the runner, agent tool calls, scorer, policy selection, aggregation, and report serialization. Keep these tests separate from live provider evaluation.

### End-to-end smoke tests

Run against a configured hosted provider only on-demand or in a protected CI job. Do not make ordinary CI depend on external provider uptime or free-tier availability.

## 2. Required routing tests

- Short straightforward task routes to the expected baseline tier.
- Code/debug task routes to strong under the configured policy.
- Multi-step task routes according to rules.
- Forced benchmark policy selects the required tier.
- Context/output capability violation is handled explicitly.
- Decision reason and policy version are always populated.

## 3. Required reliability tests

- One retryable failure followed by success.
- Exhausted retry budget.
- 429 with `Retry-After`.
- Non-retryable 4xx is not retried.
- Fallback success and fallback failure.
- Deadline prevents late retry/fallback.
- Cache unavailable does not block request.
- Missing token usage or rate-card data is marked accurately.

## 4. CI quality gates

Formatting/lint, type checks, unit tests, integration tests with mocks, migration tests, security/dependency scan, and build/container smoke test. Live API calls are not a required default gate.

## 5. Test data integrity

Use synthetic prompts and deterministic tool fixtures. Do not store real private user conversations in the public benchmark dataset. Every expected answer and scorer change must be reviewed and versioned.
