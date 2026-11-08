# Testing Strategy

## 1. Unit tests

Test without network calls:
- routing feature extraction
- model eligibility checks
- route decision and reason codes
- cost calculation
- retry eligibility
- fallback selection
- cache-key generation
- scorer functions
- schema validation

## 2. Provider contract tests

Use mocked HTTP responses to test:
- successful response normalization
- usage extraction
- timeout mapping
- rate-limit mapping
- authentication error mapping
- malformed provider response handling

## 3. Integration tests

- API request reaches mocked adapter.
- Request and attempt records are persisted.
- Retry and fallback events are correlated.
- Cache hit avoids provider invocation.
- Client cannot inspect another client's request.
- Evaluation runner stores per-case results.

## 4. Failure-injection tests

Simulate:
- provider timeout
- 429 rate limit
- provider 500
- invalid API key
- unavailable fallback
- database write failure
- malformed provider payload

Assert bounded execution and correct error reporting.

## 5. Evaluation tests

- Dataset schema is valid.
- Every task has a scorer.
- Repeated runs preserve task identity.
- Policy comparison uses the same dataset version.
- Unknown token/cost values remain unknown.
- Aggregate metrics reconcile with per-case results.

## 6. CI quality gates

At minimum:
- formatting/linting
- type checks where used
- unit tests
- mocked integration tests
- small deterministic evaluation smoke test

Do not make CI depend on a paid live model call for every commit. Keep live-provider tests optional or scheduled.
