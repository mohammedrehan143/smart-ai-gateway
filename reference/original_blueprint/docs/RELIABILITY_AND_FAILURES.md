# Reliability and Failure Handling

## 1. Principles

- Every retry is bounded.
- Retry only errors likely to be transient.
- Respect the overall request deadline.
- Do not retry invalid requests or credential failures.
- Fallback must preserve required capabilities.
- Every attempt is recorded.

## 2. Retry policy

Suggested starting configuration (tune using tests):
- maximum retries: 2 (three total attempts including the first)
- exponential backoff with jitter
- per-attempt timeout: configured per model
- overall deadline: shorter than the client/proxy timeout

Do not sleep/retry past the request deadline.

## 3. Retryable errors

Usually retryable:
- network interruption
- timeout
- provider 5xx
- rate limit, when retry window fits the deadline

Usually not retryable:
- malformed request
- unsupported capability
- invalid credentials
- permission denied
- context too long (unless request is deliberately transformed by a separate supported policy)

## 4. Fallback

Fallback target must:
- be enabled and healthy
- support all hard request requirements
- have a configured relationship to the primary target
- be included in cost/quality reporting

Record `fallback_from`, `fallback_to`, and the triggering error category.

## 5. Circuit breaker (later phase)

A circuit breaker can temporarily stop calls to a repeatedly failing provider:
- closed: normal calls
- open: reject or route elsewhere
- half-open: allow limited probe calls

Do not add a complex breaker before basic bounded retries and fallback are tested.

## 6. Idempotency

Provider calls may not be idempotent in every context. Avoid blind retries for requests that trigger external side effects or tool execution. The MVP should focus on text generation without external side effects, or require idempotency support for tool actions.

## 7. Operational signals

Track:
- attempts per request
- retry count
- fallback count
- provider error rate
- timeout rate
- circuit state (if implemented)
- time spent waiting between attempts
